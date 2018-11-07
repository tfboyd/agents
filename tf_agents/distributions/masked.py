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

"""Define distributions for spaces where not all actions are valid."""
import tensorflow as tf


class MaskedCategorical(tf.distributions.Categorical):
  """A categorical distribution which supports masks per step.

  Masked values are replaced with -inf inside the logits. This means the values
  will never be sampled.

  When computing the log probability of a set of actions, each action is
  assigned a probability under each sample. _log_prob is modified to only return
  the probability of a sample under the distribution for the same timestep.

  TODO(ddohan): Integrate entropy calculation from cl/207017752
  """

  def __init__(self,
               logits,
               mask,
               dtype=tf.int32,
               validate_args=False,
               allow_nan_stats=True,
               name='MaskedCategorical'):
    """Initialize Categorical distributions using class log-probabilities.

    Args:
      logits: An N-D `Tensor`, `N >= 1`, representing the log probabilities of a
        set of Categorical distributions. The first `N - 1` dimensions index
        into a batch of independent distributions and the last dimension
        represents a vector of logits for each class. Only one of `logits` or
        `probs` should be passed in.
      mask: A boolean mask. False/0 values mean a position should be masked out.
      dtype: The type of the event samples (default: int32).
      validate_args: Python `bool`, default `False`. When `True` distribution
        parameters are checked for validity despite possibly degrading runtime
        performance. When `False` invalid inputs may silently render incorrect
        outputs.
      allow_nan_stats: Python `bool`, default `True`. When `True`, statistics
        (e.g., mean, mode, variance) use the value "`NaN`" to indicate the
        result is undefined. When `False`, an exception is raised if one or more
        of the statistic's batch members are undefined.
      name: Python `str` name prefixed to Ops created by this class.
    """
    logits = tf.convert_to_tensor(logits)
    mask = tf.convert_to_tensor(mask)
    mask = tf.cast(mask, tf.bool)  # Nonzero values are True

    neg_inf = tf.cast(tf.fill(dims=tf.shape(logits), value=float('-inf')),
                      logits.dtype)

    logits = tf.where(mask, logits, neg_inf)
    super(MaskedCategorical, self).__init__(
        logits=logits,
        probs=None,
        dtype=dtype,
        validate_args=validate_args,
        allow_nan_stats=allow_nan_stats,
        name=name)
