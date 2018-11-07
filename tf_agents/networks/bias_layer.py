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

"""Keras layer mirroring tf.contrib.layers.bias_add."""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf


class BiasLayer(tf.keras.layers.Layer):
  """Keras layer that only adds a bias to the input.

  `BiasLayer` implements the operation:
  `output = input + bias`

  Arguments:
      bias_initializer: Initializer for the bias vector.
  Input shape:
      nD tensor with shape: `(batch_size, ..., input_dim)`. The most common
        situation would be a 2D input with shape `(batch_size, input_dim)`. Note
        a rank of at least 2 is required.
  Output shape:
      nD tensor with shape: `(batch_size, ..., input_dim)`. For instance, for a
        2D input with shape `(batch_size, input_dim)`, the output would have
        shape `(batch_size, input_dim)`.
  """

  def __init__(self, bias_initializer='zeros', **kwargs):
    if 'input_shape' not in kwargs and 'input_dim' in kwargs:
      kwargs['input_shape'] = (kwargs.pop('input_dim'),)

    super(BiasLayer, self).__init__(**kwargs)
    self.bias_initializer = tf.keras.initializers.get(bias_initializer)

    self.supports_masking = True
    self.input_spec = tf.keras.layers.InputSpec(min_ndim=2)

  def build(self, input_shape):
    input_shape = tf.TensorShape(input_shape)

    if input_shape[-1].value is None:
      raise ValueError('The last dimension of the inputs to `BiasLayer` '
                       'should be defined. Found `None`.')

    self.input_spec = tf.keras.layers.InputSpec(
        min_ndim=2, axes={-1: input_shape[-1].value})
    self.bias = self.add_weight(
        'bias',
        shape=[input_shape[-1]],
        initializer=self.bias_initializer,
        dtype=self.dtype,
        trainable=True)
    self.built = True

  def call(self, inputs):
    return tf.nn.bias_add(inputs, self.bias)

  def compute_output_shape(self, input_shape):
    return input_shape

  def get_config(self):
    config = {
        'bias_initializer':
            tf.keras.initializers.serialize(self.bias_initializer),
    }
    base_config = super(BiasLayer, self).get_config()
    return dict(list(base_config.items()) + list(config.items()))
