# coding=utf-8
# Copyright 2018 The TF-Agents Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""An ActorPolicy that also returns policy_info needed for PPO training."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
import tensorflow_probability as tfp

from tf_agents.agents.ppo import ppo_utils
from tf_agents.environments import time_step as ts
from tf_agents.policies import actor_policy
from tf_agents.policies import policy_step
from tf_agents.utils import common as common_utils
from tensorflow.python.ops import template  # TF internal

nest = tf.contrib.framework.nest
tfd = tfp.distributions


class PPOPolicy(actor_policy.ActorPolicy):
  """An ActorPolicy that also returns policy_info needed for PPO training."""

  def __init__(self,
               time_step_spec=None,
               action_spec=None,
               policy_state_spec=(),
               actor_network=None,
               value_network=None,
               template_name='actor_policy',
               value_template_name='value_network',
               observation_normalizer=None,
               clip=True,
               collect=True):
    """Builds a PPO Policy given network Templates or functions.

    Args:
      time_step_spec: A `TimeStep` spec of the expected time_steps.
      action_spec: A nest of BoundedTensorSpec representing the actions.
      policy_state_spec: A nest of TensorSpec representing policy network state.
      actor_network: A Template from tf.make_template or a function. When
        passing a Template the variables will be reused, passing a function it
        will create a new template with a new set variables.  Network should
        return one of the following:
          1. a nested tuple of tf.distributions objects matching action_spec, or
          2. a nested tuple of tf.Tensors representing actions.
      value_network: A Template from tf.make_template or a function. When
        passing a Template the variables will be reused, passing a function it
        will create a new template with a new set variables.  Network should
        return value predictions for the input state.
      template_name: Name to use for the new template. Ignored if actor_network
        is already a template.
      value_template_name: Name to use for the new value function template.
        Ignored if value_network is already a template.
      observation_normalizer: An object to use for obervation normalization.
      clip: Whether to clip actions to spec before returning them.  Default
        True. Most policy-based algorithms (PCL, PPO, REINFORCE) use unclipped
        continuous actions for training.
      collect: If True, creates ops for actions_log_prob, value_preds, and
        action_distribution_params. (default True)
    Raises:
      ValueError: if actor_network or value_network is not of type callable or
        tensorflow.python.ops.template.Template.
    """
    super(PPOPolicy, self).__init__(
        time_step_spec=time_step_spec, action_spec=action_spec,
        policy_state_spec=policy_state_spec, actor_network=actor_network,
        template_name=template_name,
        observation_normalizer=observation_normalizer, clip=clip)
    self._collect = collect

    # Set self._value_network based on type of argument.
    if isinstance(value_network, template.Template):
      self._value_network = value_network
    elif callable(value_network):
      self._value_network = tf.make_template(
          value_template_name, value_network, create_scope_now_=True)
    else:
      raise ValueError('Unrecognized type for arg value_network: %s (%s)' %
                       (value_network, type(value_network)))

    # TODO(ebrevdo,eholly): Fix this.  Hacky way to set up info_spec.
    # Instead, the info_spec should be determined from __init__ arguments and
    # passed to super().
    if self._collect:
      self._info_spec = ppo_utils.get_distribution_params_spec(
          policy=self, time_step_spec=time_step_spec)
      self._setup_specs()

  def apply_value_network(self, observations, step_types, policy_state):
    """Apply value network to time_step, potentially a sequence.

    If observation_normalizer is not None, applies observation normalization.

    Args:
      observations: A (possibly nested) observation tensor with outer_dims
        either (batch_size,) or (batch_size, time_index). If observations is a
        time series and network is RNN, will run RNN steps over time series.
      step_types: A (possibly nested) step_types tensor with same outer_dims as
        observations.
      policy_state: Initial policy state for value_network.
    Returns:
      The output of value_net, which is a tuple of:
        - value_preds with same outer_dims as time_step
        - policy_state at the end of the time series
    """
    if self._observation_normalizer:
      observations = self._observation_normalizer.normalize(observations)
    return self._value_network(observations, step_types, policy_state)

  def _apply_actor_network(self, time_step, policy_state):
    if self._observation_normalizer:
      observation = self._observation_normalizer.normalize(
          time_step.observation)
      time_step = ts.TimeStep(time_step.step_type, time_step.reward,
                              time_step.discount, observation)
    return self._actor_network(time_step, self._action_spec,
                               network_state=policy_state)

  def _variables(self):
    var_list = self._actor_variables()
    var_list += self._value_network.global_variables[:]
    return var_list

  def _action(self, time_step, policy_state, seed):
    seed_stream = tfd.SeedStream(seed=seed, salt='ppo_policy')

    def _sample(dist, action_spec):
      action = dist.sample(seed=seed_stream())
      if self._clip:
        return common_utils.clip_to_spec(action, action_spec)
      return action

    distribution_step = self.distribution(time_step, policy_state)
    actions = nest.map_structure(
        _sample, distribution_step.action, self._action_spec)

    return policy_step.PolicyStep(actions,
                                  distribution_step.state,
                                  distribution_step.info)

  def _distribution(self, time_step, policy_state):
    # Actor network outputs nested structure of distributions or actions.
    actions_or_distributions, policy_state = self._apply_actor_network(
        time_step, policy_state)

    def _to_distribution(action_or_distribution):
      if isinstance(action_or_distribution, tf.Tensor):
        # This is an action tensor, so wrap it in a deterministic distribution.
        return tfp.distributions.Deterministic(loc=action_or_distribution)
      return action_or_distribution

    distributions = nest.map_structure(_to_distribution,
                                       actions_or_distributions)

    # Prepare policy_info.
    if self._collect:
      policy_info = ppo_utils.get_distribution_params(distributions)
    else:
      policy_info = ()

    return policy_step.PolicyStep(distributions, policy_state, policy_info)
