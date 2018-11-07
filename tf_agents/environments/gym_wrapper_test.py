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

"""Tests for environments.gym_wrapper."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math

from absl.testing import absltest
import gym
import gym.spaces
import mock
import numpy as np

from tf_agents.environments import gym_wrapper


class GymWrapperSpecTest(absltest.TestCase):

  def test_spec_from_gym_space_discrete(self):
    discrete_space = gym.spaces.Discrete(3)
    spec = gym_wrapper._spec_from_gym_space(discrete_space)

    self.assertEqual((1,), spec.shape)
    self.assertEqual(np.int64, spec.dtype)
    self.assertEqual(0, spec.minimum)
    self.assertEqual(2, spec.maximum)

  def test_spec_from_gym_space_box_scalars(self):
    box_space = gym.spaces.Box(-1.0, 1.0, (3, 4))
    spec = gym_wrapper._spec_from_gym_space(box_space)

    self.assertEqual((3, 4), spec.shape)
    self.assertEqual(np.float32, spec.dtype)
    np.testing.assert_array_almost_equal(-np.ones((3, 4)), spec.minimum)
    np.testing.assert_array_almost_equal(np.ones((3, 4)), spec.maximum)

  def test_spec_from_gym_space_box_array(self):
    box_space = gym.spaces.Box(np.array([-1.0, -2.0]), np.array([2.0, 4.0]))
    spec = gym_wrapper._spec_from_gym_space(box_space)

    self.assertEqual((2,), spec.shape)
    self.assertEqual(np.float32, spec.dtype)
    np.testing.assert_array_almost_equal(np.array([-1.0, -2.0]), spec.minimum)
    np.testing.assert_array_almost_equal(np.array([2.0, 4.0]), spec.maximum)

  def test_spec_from_gym_space_tuple(self):
    tuple_space = gym.spaces.Tuple((gym.spaces.Discrete(2),
                                    gym.spaces.Discrete(3)))
    spec = gym_wrapper._spec_from_gym_space(tuple_space)

    self.assertEqual(2, len(spec))
    self.assertEqual((1,), spec[0].shape)
    self.assertEqual(np.int64, spec[0].dtype)
    self.assertEqual(0, spec[0].minimum)
    self.assertEqual(1, spec[0].maximum)

    self.assertEqual((1,), spec[1].shape)
    self.assertEqual(np.int64, spec[1].dtype)
    self.assertEqual(0, spec[1].minimum)
    self.assertEqual(2, spec[1].maximum)

  def test_spec_from_gym_space_tuple_mixed(self):
    tuple_space = gym.spaces.Tuple((
        gym.spaces.Discrete(2),
        gym.spaces.Box(-1.0, 1.0, (3, 4)),
        gym.spaces.Tuple((gym.spaces.Discrete(2), gym.spaces.Discrete(3))),
        gym.spaces.Dict({
            'spec_1':
                gym.spaces.Discrete(2),
            'spec_2':
                gym.spaces.Tuple((gym.spaces.Discrete(2),
                                  gym.spaces.Discrete(3))),
        }),
    ))
    spec = gym_wrapper._spec_from_gym_space(tuple_space)

    self.assertEqual(4, len(spec))
    # Test Discrete
    self.assertEqual((1,), spec[0].shape)
    self.assertEqual(np.int64, spec[0].dtype)
    self.assertEqual(0, spec[0].minimum)
    self.assertEqual(1, spec[0].maximum)

    # Test Box
    self.assertEqual((3, 4), spec[1].shape)
    self.assertEqual(np.float32, spec[1].dtype)
    np.testing.assert_array_almost_equal(-np.ones((3, 4)), spec[1].minimum)
    np.testing.assert_array_almost_equal(np.ones((3, 4)), spec[1].maximum)

    # Test Tuple
    self.assertEqual(2, len(spec[2]))
    self.assertEqual((1,), spec[2][0].shape)
    self.assertEqual(np.int64, spec[2][0].dtype)
    self.assertEqual(0, spec[2][0].minimum)
    self.assertEqual(1, spec[2][0].maximum)
    self.assertEqual((1,), spec[2][1].shape)
    self.assertEqual(np.int64, spec[2][1].dtype)
    self.assertEqual(0, spec[2][1].minimum)
    self.assertEqual(2, spec[2][1].maximum)

    # Test Dict
    # Test Discrete in Dict
    discrete_in_dict = spec[3]['spec_1']
    self.assertEqual((1,), discrete_in_dict.shape)
    self.assertEqual(np.int64, discrete_in_dict.dtype)
    self.assertEqual(0, discrete_in_dict.minimum)
    self.assertEqual(1, discrete_in_dict.maximum)

    # Test Tuple in Dict
    tuple_in_dict = spec[3]['spec_2']
    self.assertEqual(2, len(tuple_in_dict))
    self.assertEqual((1,), tuple_in_dict[0].shape)
    self.assertEqual(np.int64, tuple_in_dict[0].dtype)
    self.assertEqual(0, tuple_in_dict[0].minimum)
    self.assertEqual(1, tuple_in_dict[0].maximum)
    self.assertEqual((1,), tuple_in_dict[1].shape)
    self.assertEqual(np.int64, tuple_in_dict[1].dtype)
    self.assertEqual(0, tuple_in_dict[1].minimum)
    self.assertEqual(2, tuple_in_dict[1].maximum)

  def test_spec_from_gym_space_dict(self):
    dict_space = gym.spaces.Dict({
        'spec_1': gym.spaces.Discrete(2),
        'spec_2': gym.spaces.Box(-1.0, 1.0, (3, 4)),
    })
    spec = gym_wrapper._spec_from_gym_space(dict_space)

    self.assertEqual(2, len(spec))
    self.assertEqual((1,), spec['spec_1'].shape)
    self.assertEqual(np.int64, spec['spec_1'].dtype)
    self.assertEqual(0, spec['spec_1'].minimum)
    self.assertEqual(1, spec['spec_1'].maximum)

    self.assertEqual((3, 4), spec['spec_2'].shape)
    self.assertEqual(np.float32, spec['spec_2'].dtype)
    np.testing.assert_array_almost_equal(
        -np.ones((3, 4)),
        spec['spec_2'].minimum,
    )
    np.testing.assert_array_almost_equal(
        np.ones((3, 4)),
        spec['spec_2'].maximum,
    )

  def test_spec_from_gym_space_dtype_map(self):
    tuple_space = gym.spaces.Tuple((
        gym.spaces.Discrete(2),
        gym.spaces.Box(0, 1, (3, 4)),
        gym.spaces.Tuple((gym.spaces.Discrete(2), gym.spaces.Discrete(3))),
        gym.spaces.Dict({
            'spec_1':
                gym.spaces.Discrete(2),
            'spec_2':
                gym.spaces.Tuple((
                    gym.spaces.Discrete(2),
                    gym.spaces.Box(0, 1, (3, 4)),
                )),
        }),
    ))

    dtype_map = {gym.spaces.Discrete: np.uint8, gym.spaces.Box: np.uint16}
    spec = gym_wrapper._spec_from_gym_space(tuple_space, dtype_map=dtype_map)
    self.assertEqual(np.uint8, spec[0].dtype)
    self.assertEqual(np.uint16, spec[1].dtype)
    self.assertEqual(np.uint8, spec[2][0].dtype)
    self.assertEqual(np.uint8, spec[2][1].dtype)
    self.assertEqual(np.uint8, spec[3]['spec_1'].dtype)
    self.assertEqual(np.uint8, spec[3]['spec_2'][0].dtype)
    self.assertEqual(np.uint16, spec[3]['spec_2'][1].dtype)


class GymWrapperOnCartpoleTest(absltest.TestCase):

  def test_wrapped_cartpole_specs(self):
    # Note we use spec.make on gym envs to avoid getting a TimeLimit wrapper on
    # the environment.
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)

    action_spec = env.action_spec()
    self.assertEqual((1,), action_spec.shape)
    self.assertEqual(0, action_spec.minimum)
    self.assertEqual(1, action_spec.maximum)

    observation_spec = env.observation_spec()
    self.assertEqual((4,), observation_spec.shape)
    self.assertEqual(np.float32, observation_spec.dtype)
    high = np.array([
        4.8,
        np.finfo(np.float32).max, 2 / 15.0 * math.pi,
        np.finfo(np.float32).max
    ])
    np.testing.assert_array_almost_equal(-high, observation_spec.minimum)
    np.testing.assert_array_almost_equal(high, observation_spec.maximum)

  def test_wrapped_cartpole_reset(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)

    first_time_step = env.reset()
    self.assertTrue(first_time_step.is_first())
    self.assertEqual(0.0, first_time_step.reward)
    self.assertEqual(1.0, first_time_step.discount)
    self.assertEqual((4,), first_time_step.observation.shape)
    self.assertEqual(np.float32, first_time_step.observation.dtype)

  def test_wrapped_cartpole_transition(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    env.reset()
    transition_time_step = env.step([0])

    self.assertTrue(transition_time_step.is_mid())
    self.assertNotEqual(None, transition_time_step.reward)
    self.assertEqual(1.0, transition_time_step.discount)
    self.assertEqual((4,), transition_time_step.observation.shape)

  def test_wrapped_cartpole_final(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    time_step = env.reset()

    while not time_step.is_last():
      time_step = env.step([1])

    self.assertTrue(time_step.is_last())
    self.assertNotEqual(None, time_step.reward)
    self.assertEqual(0.0, time_step.discount)
    self.assertEqual((4,), time_step.observation.shape)

  def test_get_info(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    self.assertEqual(None, env.get_info())
    env.reset()
    self.assertEqual(None, env.get_info())
    env.step([0])
    self.assertEqual({}, env.get_info())

  def test_automatic_reset_after_create(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)

    first_time_step = env.step([0])
    self.assertTrue(first_time_step.is_first())

  def test_automatic_reset_after_done(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    time_step = env.reset()

    while not time_step.is_last():
      time_step = env.step([1])

    self.assertTrue(time_step.is_last())
    first_time_step = env.step([0])
    self.assertTrue(first_time_step.is_first())

  def test_automatic_reset_after_done_not_using_reset_directly(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    time_step = env.step([1])

    while not time_step.is_last():
      time_step = env.step([1])

    self.assertTrue(time_step.is_last())
    first_time_step = env.step([0])
    self.assertTrue(first_time_step.is_first())

  def test_render(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    cartpole_env.render = mock.MagicMock()
    env = gym_wrapper.GymWrapper(cartpole_env)
    env.render()
    cartpole_env.render.assert_called_once()

  def test_obs_dtype(self):
    cartpole_env = gym.spec('CartPole-v1').make()
    env = gym_wrapper.GymWrapper(cartpole_env)
    time_step = env.reset()
    self.assertEqual(env.observation_spec().dtype, time_step.observation.dtype)


if __name__ == '__main__':
  absltest.main()
