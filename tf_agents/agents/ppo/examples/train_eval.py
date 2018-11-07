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

r"""Train and Eval PPO.

To run:

```bash
tensorboard --logdir ~/tmp/ppo --port 2223 &

tf_agents/agents/ppo/examples/train_eval.py -- \
  --root_dir=~/tmp/ppo_example --logtostderr
```
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import functools
import os
import time
from absl import flags

import tensorflow as tf

from tf_agents.agents.ppo import networks
from tf_agents.agents.ppo import ppo_agent
from tf_agents.agents.ppo import rnn_networks
from tf_agents.drivers import dynamic_episode_driver
from tf_agents.environments import parallel_py_environment
from tf_agents.environments import suite_mujoco
from tf_agents.environments import tf_py_environment
from tf_agents.metrics import batched_py_metric
from tf_agents.metrics import metric_utils
from tf_agents.metrics import tf_metrics
from tf_agents.metrics.py_metrics import AverageEpisodeLengthMetric
from tf_agents.metrics.py_metrics import AverageReturnMetric
from tf_agents.policies import py_tf_policy
from tf_agents.replay_buffers import batched_replay_buffer
from tf_agents.utils import common as common_utils
import gin


nest = tf.contrib.framework.nest

flags.DEFINE_string('root_dir', os.getenv('TEST_UNDECLARED_OUTPUTS_DIR'),
                    'Root directory for writing logs/summaries/checkpoints.')
flags.DEFINE_string('master', '', 'master session')
flags.DEFINE_string('env_name', 'HalfCheetah-v1', 'Name of an environment')
flags.DEFINE_integer('replay_buffer_capacity', 1001,
                     'Replay buffer capacity per env.')
flags.DEFINE_integer('num_parallel_environments', 30,
                     'Number of environments to run in parallel')
flags.DEFINE_integer('num_environment_steps', 10000000,
                     'Number of environment steps to run before finishing.')
flags.DEFINE_integer('num_epochs', 25,
                     'Number of epochs for computing policy updates.')
flags.DEFINE_integer('collect_episodes_per_iteration', 30,
                     'The number of episodes to take in the environment before '
                     'each update. This is the total across all parallel '
                     'environments.')
flags.DEFINE_integer('num_eval_episodes', 30,
                     'The number of episodes to run eval on.')
flags.DEFINE_boolean('use_rnns', False,
                     'If true, use RNN for policy and value function.')
FLAGS = flags.FLAGS


@gin.configurable
def train_eval(
    root_dir,
    tf_master='',
    env_name='HalfCheetah-v1',
    env_load_fn=suite_mujoco.load,
    random_seed=0,
    # TODO(kbanoop): rename to policy_fc_layers.
    actor_fc_layers=(200, 100),
    value_fc_layers=(200, 100),
    use_rnns=False,
    # Params for collect
    num_environment_steps=10000000,
    collect_episodes_per_iteration=30,
    num_parallel_environments=30,
    replay_buffer_capacity=1001,  # Per-environment
    # Params for train
    num_epochs=25,
    learning_rate=1e-4,
    # Params for eval
    num_eval_episodes=30,
    eval_interval=500,
    # Params for summaries and logging
    train_checkpoint_interval=100,
    policy_checkpoint_interval=50,
    rb_checkpoint_interval=200,
    log_interval=50,
    summary_interval=50,
    summaries_flush_secs=1,
    debug_summaries=False,
    summarize_grads_and_vars=False,
    eval_metrics_callback=None):
  """A simple train and eval for PPO."""
  if root_dir is None:
    raise AttributeError('train_eval requires a root_dir.')

  root_dir = os.path.expanduser(root_dir)
  train_dir = os.path.join(root_dir, 'train')
  eval_dir = os.path.join(root_dir, 'eval')

  train_summary_writer = tf.contrib.summary.create_file_writer(
      train_dir, flush_millis=summaries_flush_secs * 1000)
  train_summary_writer.set_as_default()

  eval_summary_writer = tf.contrib.summary.create_file_writer(
      eval_dir, flush_millis=summaries_flush_secs * 1000)
  eval_metrics = [
      batched_py_metric.BatchedPyMetric(
          AverageReturnMetric,
          metric_args={'buffer_size': num_eval_episodes},
          batch_size=num_parallel_environments),
      batched_py_metric.BatchedPyMetric(
          AverageEpisodeLengthMetric,
          metric_args={'buffer_size': num_eval_episodes},
          batch_size=num_parallel_environments),
  ]
  eval_summary_writer_flush_op = eval_summary_writer.flush()

  # TODO(kbanoop): Figure out if it is possible to avoid the with block.
  with tf.contrib.summary.record_summaries_every_n_global_steps(
      summary_interval):
    tf.set_random_seed(random_seed)
    eval_py_env = parallel_py_environment.ParallelPyEnvironment(
        [lambda: env_load_fn(env_name)] * num_parallel_environments)
    tf_env = tf_py_environment.TFPyEnvironment(
        parallel_py_environment.ParallelPyEnvironment(
            [lambda: env_load_fn(env_name)] * num_parallel_environments))
    time_step_spec = tf_env.time_step_spec()
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)

    if use_rnns:
      # TODO(kbanoop): Handle distributions without gin.
      actor_net = functools.partial(
          rnn_networks.actor_network, fc_layers=actor_fc_layers,
          time_step_spec=time_step_spec)
      value_net = functools.partial(
          rnn_networks.value_network, fc_layers=value_fc_layers,
          observation_spec=time_step_spec.observation)
      policy_state_spec = rnn_networks.get_state_spec()
    else:
      # TODO(kbanoop): Handle distributions without gin.
      actor_net = functools.partial(
          networks.actor_network, fc_layers=actor_fc_layers,
          time_step_spec=time_step_spec)
      value_net = functools.partial(
          networks.value_network, fc_layers=value_fc_layers,
          observation_spec=time_step_spec.observation)
      policy_state_spec = ()

    tf_agent = ppo_agent.PPOAgent(
        tf_env.time_step_spec(),
        tf_env.action_spec(),
        optimizer,
        policy_state_spec=policy_state_spec,
        actor_net=actor_net,
        value_net=value_net,
        num_epochs=num_epochs,
        debug_summaries=debug_summaries,
        summarize_grads_and_vars=summarize_grads_and_vars)

    replay_buffer = batched_replay_buffer.BatchedReplayBuffer(
        tf_agent.collect_data_spec(),
        batch_size=num_parallel_environments,
        max_length=replay_buffer_capacity)

    eval_py_policy = py_tf_policy.PyTFPolicy(
        tf_agent.policy(), batch_size=num_parallel_environments)

    # TODO(sguada): Reenable metrics when ready for batch data.
    environment_steps_metric = tf_metrics.EnvironmentSteps()
    environment_steps_metric.build()
    environment_steps_count = environment_steps_metric.value()
    step_metrics = [
        tf_metrics.NumberOfEpisodes(),
        environment_steps_metric,
    ]
    train_metrics = step_metrics + [
        tf_metrics.AverageReturnMetric(),
        tf_metrics.AverageEpisodeLengthMetric(),
    ]

    # Add to replay buffer and other agent specific observers.
    replay_buffer_observer = [replay_buffer.add_batch]

    global_step = tf.train.get_or_create_global_step()
    collect_policy = tf_agent.collect_policy()

    policy_state = tf_agent.policy().get_initial_state(
        batch_size=tf_env.batch_size)

    collect_op = dynamic_episode_driver.DynamicEpisodeDriver(
        tf_env,
        collect_policy,
        observers=replay_buffer_observer + train_metrics,
        num_episodes=collect_episodes_per_iteration).run(
            policy_state=policy_state)

    trajectories, _ = replay_buffer.gather_all()

    train_op = tf_agent.train(experience=trajectories,
                              train_step_counter=global_step)

    with tf.control_dependencies([train_op]):
      clear_replay_op = replay_buffer.clear()

    with tf.control_dependencies([clear_replay_op]):
      train_op = tf.identity(train_op)

    train_checkpointer = common_utils.Checkpointer(
        ckpt_dir=train_dir,
        agent=tf_agent,
        global_step=global_step,
        metrics=tf.contrib.checkpoint.List(train_metrics))
    policy_checkpointer = common_utils.Checkpointer(
        ckpt_dir=os.path.join(train_dir, 'policy'),
        policy=tf_agent.policy(),
        global_step=global_step)
    rb_checkpointer = common_utils.Checkpointer(
        ckpt_dir=os.path.join(train_dir, 'replay_buffer'),
        max_to_keep=1,
        replay_buffer=replay_buffer)

    for train_metric in train_metrics:
      train_metric.tf_summaries()
    summary_op = tf.contrib.summary.all_summary_ops()

    with eval_summary_writer.as_default(), \
         tf.contrib.summary.always_record_summaries():
      for eval_metric in eval_metrics:
        eval_metric.tf_summaries(step_metrics=step_metrics)

    init_agent_op = tf_agent.initialize()

    with tf.Session(tf_master) as sess:
      # Initialize graph.
      train_checkpointer.initialize_or_restore(sess)
      rb_checkpointer.initialize_or_restore(sess)
      # TODO(sguada) Remove once Periodically can be saved.
      common_utils.initialize_uninitialized_variables(sess)

      sess.run(init_agent_op)
      tf.contrib.summary.initialize(session=sess)

      collect_time = 0
      train_time = 0
      timed_at_step = sess.run(global_step)
      steps_per_second_ph = tf.placeholder(
          tf.float32, shape=(), name='steps_per_sec_ph')
      steps_per_second_summary = tf.contrib.summary.scalar(
          name='global_steps/sec', tensor=steps_per_second_ph)

      while sess.run(environment_steps_count) < num_environment_steps:
        global_step_val = sess.run(global_step)
        if global_step_val % eval_interval == 0:
          metric_utils.compute_summaries(
              eval_metrics,
              eval_py_env,
              eval_py_policy,
              num_episodes=num_eval_episodes,
              global_step=global_step_val,
              callback=eval_metrics_callback,
          )
          sess.run(eval_summary_writer_flush_op)

        start_time = time.time()
        sess.run(collect_op)
        collect_time += time.time() - start_time
        start_time = time.time()
        total_loss, _ = sess.run([train_op, summary_op])
        train_time += time.time() - start_time

        global_step_val = sess.run(global_step)
        if global_step_val % log_interval == 0:
          tf.logging.info('step = %d, loss = %f', global_step_val, total_loss)
          steps_per_sec = ((global_step_val - timed_at_step) /
                           (collect_time + train_time))
          tf.logging.info('%.3f steps/sec' % steps_per_sec)
          sess.run(
              steps_per_second_summary,
              feed_dict={steps_per_second_ph: steps_per_sec})
          tf.logging.info('collect_time = {}, train_time = {}'.format(
              collect_time, train_time))
          timed_at_step = global_step_val
          collect_time = 0
          train_time = 0

        if global_step_val % train_checkpoint_interval == 0:
          train_checkpointer.save(global_step=global_step_val)

        if global_step_val % policy_checkpoint_interval == 0:
          policy_checkpointer.save(global_step=global_step_val)

        if global_step_val % rb_checkpoint_interval == 0:
          rb_checkpointer.save(global_step=global_step_val)

      # One final eval before exiting.
      metric_utils.compute_summaries(
          eval_metrics,
          eval_py_env,
          eval_py_policy,
          num_episodes=num_eval_episodes,
          global_step=global_step_val,
          callback=eval_metrics_callback,
      )
      sess.run(eval_summary_writer_flush_op)


def main(_):
  tf.logging.set_verbosity(tf.logging.INFO)
  train_eval(
      FLAGS.root_dir, tf_master=FLAGS.master,
      env_name=FLAGS.env_name,
      replay_buffer_capacity=FLAGS.replay_buffer_capacity,
      num_environment_steps=FLAGS.num_environment_steps,
      num_parallel_environments=FLAGS.num_parallel_environments,
      num_epochs=FLAGS.num_epochs,
      collect_episodes_per_iteration=FLAGS.collect_episodes_per_iteration,
      num_eval_episodes=FLAGS.num_eval_episodes,
      use_rnns=FLAGS.use_rnns)


if __name__ == '__main__':
  flags.mark_flag_as_required('root_dir')
  tf.app.run()
