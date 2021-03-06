from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
os.environ['RAY_DEBUG_DISABLE_MEMORY_MONITOR'] = "True"

import argparse
import gym
import random
import numpy as np

import ray
from ray import tune
from ray.rllib.utils import try_import_tf
from ray.tune.registry import register_env
from ray.rllib.models.tf.tf_modelv2 import TFModelV2
from ray.rllib.models.tf.fcnet_v2 import FullyConnectedNetwork
from ray.rllib.models import Model, ModelCatalog
from ray.rllib.policy.policy import Policy
from ray.rllib.agents.ppo.ppo import PPOTrainer
from ray.rllib.agents.ppo.ppo_tf_policy import PPOTFPolicy

import sys
if "../" not in sys.path:
    sys.path.append("../")

from gym_continuousDoubleAuction.envs.continuousDoubleAuction_env import continuousDoubleAuctionEnv

tf = try_import_tf()


parser = argparse.ArgumentParser()
parser.add_argument("--num-agents", type=int, default=4)
parser.add_argument("--num-policies", type=int, default=4)
parser.add_argument("--num-iters", type=int, default=2)
parser.add_argument("--simple", action="store_true")


class CustomModel_disc(Model):
    def _lstm(self, Inputs, cell_size):
        s = tf.expand_dims(Inputs, axis=1, name='time_major')  # [time_step, feature] => [time_step, batch, feature]
        lstm_cell = tf.nn.rnn_cell.LSTMCell(cell_size)
        self.init_state = lstm_cell.zero_state(batch_size=1, dtype=tf.float32)
        # time_major means [time_step, batch, feature] while batch major means [batch, time_step, feature]
        outputs, self.final_state = tf.nn.dynamic_rnn(cell=lstm_cell, inputs=s, initial_state=self.init_state, time_major=True)
        lstm_out = tf.reshape(outputs, [-1, cell_size], name='flatten_rnn_outputs')  # joined state representation
        return lstm_out

    def _build_layers_v2(self, input_dict, num_outputs, options):
        hidden = 8
        cell_size = 4
        #S = input_dict["obs"]
        S = tf.layers.flatten(input_dict["obs"])
        with tf.variable_scope(tf.VariableScope(tf.AUTO_REUSE, "shared"),
                               reuse=tf.AUTO_REUSE,
                               auxiliary_name_scope=False):
            last_layer = tf.layers.dense(S, hidden, activation=tf.nn.relu, name="fc1")
        last_layer = tf.layers.dense(last_layer, hidden, activation=tf.nn.relu, name="fc2")
        last_layer = tf.layers.dense(last_layer, hidden, activation=tf.nn.relu, name="fc3")

        last_layer = self._lstm(last_layer, cell_size)

        output = tf.layers.dense(last_layer, num_outputs, activation=tf.nn.softmax, name="mu")

        return output, last_layer


def make_RandomPolicy(_seed):

    # a hand-coded policy that acts at random in the env (doesn't learn)
    class RandomPolicy(Policy):
        """Hand-coded policy that returns random actions."""
        def __init__(self, observation_space, action_space, config):
            self.observation_space = observation_space
            self.action_space = action_space
            self.action_space.seed(_seed)

        def compute_actions(self,
                            obs_batch,
                            state_batches,
                            prev_action_batch=None,
                            prev_reward_batch=None,
                            info_batch=None,
                            episodes=None,
                            **kwargs):
            """Compute actions on a batch of observations."""
            return [self.action_space.sample() for _ in obs_batch], [], {}

        def learn_on_batch(self, samples):
            """No learning."""
            #return {}
            pass

        def get_weights(self):
            pass

        def set_weights(self, weights):
            pass

    return RandomPolicy


if __name__ == "__main__":
    args = parser.parse_args()

    ray.init(num_cpus=2, logging_level=0, local_mode=True, ignore_reinit_error=True, log_to_driver=False, webui_host='127.0.0.1') # local_mode for sequential trials to work in Travis which has only 2 CPU
    print(' ********** num_CPU =', os.cpu_count())

    num_agents = 4
    num_policies = num_agents
    num_iters = 3
    simple = False #store_true

    num_of_traders = args.num_agents
    tape_display_length = 100
    tick_size = 1
    init_cash = 1000000
    max_step = 500
    episode = 5

    single_CDA_env = continuousDoubleAuctionEnv(num_of_traders, init_cash, tick_size, tape_display_length, max_step)
    obs_space = single_CDA_env.observation_space
    act_space = single_CDA_env.action_space
    register_env("continuousDoubleAuction-v0", lambda _: continuousDoubleAuctionEnv(num_of_traders, init_cash, tick_size, tape_display_length, max_step))
    ModelCatalog.register_custom_model("model_disc", CustomModel_disc)


    # Each policy can have a different configuration (including custom model)
    def gen_policy(i):
        config = {"model": {"custom_model": "model_disc"},
                "gamma": 0.99,}
        return (None, obs_space, act_space, config)

    def policy_mapper(agent_id):
        for i in range(num_agents):
            if agent_id == i:
                return "policy_{}".format(i)

    # Dictionary of policies
    policies = {"policy_{}".format(i): gen_policy(i) for i in range(num_policies)}

    def set_RandomPolicy(policies):
        """
        Set 1st policy as PPO & override all other policies as RandomPolicy with
        different seed.
        """

        for i in range(num_agents):
            if i == num_agents-1:
                break
            x = i + 1
            policies["policy_{}".format(num_policies-x)] = (make_RandomPolicy(num_policies-x), obs_space, act_space, {})

        print('policies:', policies)
        return 0

    set_RandomPolicy(policies)
    policy_ids = list(policies.keys())


    tune.run(PPOTrainer,
             stop={"timesteps_total": max_step * episode},
             config={"env": "continuousDoubleAuction-v0",
                     # Number of rollout worker actors to create for parallel sampling.
                     # Setting to 0 will force rollouts to be done in the trainer actor.
                     "num_workers": 0, # Colab (only 2 CPUs or 1 GPU)
                     "num_envs_per_worker": 1,
                     "sample_batch_size": 32, # number of environment steps sampled from each environment
                     "train_batch_size": 128, # minibatch size must be >= 128, number of environment steps sampled from all available environments

                     "multiagent": {"policies_to_train": ["policy_0"],
                                    "policies": policies,
                                    "policy_mapping_fn": policy_mapper,
                                    },
                    },
                )
