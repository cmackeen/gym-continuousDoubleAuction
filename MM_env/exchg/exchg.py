from gym import spaces

from .exchg_helper import Exchg_Helper
from .orderbook import OrderBook
from .trader import Trader

# The exchange environment
class Exchg(Exchg_Helper):
    def __init__(self, num_of_agents=2, init_cash=0, tape_display_length=10, max_step=100):
        self.LOB = OrderBook(0.25, tape_display_length) # limit order book
        self.agg_LOB = {} # aggregated or consolidated LOB
        self.agg_LOB_aft = {} # aggregated or consolidated LOB after processing orders

        self.next_states = {}
        self.rewards = {}
        self.dones = {}
        self.done_set = set()
        self.infos = {}

        self.trades = {} # a trade between init_party & counter_party
        self.order_in_book = {} # unfilled orders goes to LOB

        # step when actions by all traders are executed, not tick time
        # within a step, multiple trades(ticks) could happened
        self.t_step = 0
        self.max_step = max_step

        self.init_cash = init_cash
        self.tape_display_length = tape_display_length

        # list of agents or traders
        self.agents = [Trader(ID, init_cash) for ID in range(0, num_of_agents)]

        # observation space per agent:
        # array([[ 1.,  0., -1.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
        #        [-1., -4., -4.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
        #        [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.],
        #        [ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.]])
        inf = float('inf')
        neg_inf = float('-inf')
        self.observation_space = spaces.Box(low=neg_inf, high=inf, shape=(4,10))

        # action space per agent: {'ID': 0, 'type': 'market', 'side': 'bid', 'size': 1, 'price': 8}
        self.action_space = spaces.Dict({"ID": spaces.Discrete(num_of_agents),
                                         "type": spaces.Discrete(2), # 'market', 'limit'
                                         "side": spaces.Discrete(3), # 'bid', None, 'ask'
                                         "size": spaces.Box(low=0, high=inf, shape=(1,1)),
                                         "price": spaces.Box(low=0, high=inf, shape=(1,1))})

    # reset
    def reset(self):
        self.LOB = OrderBook(0.25, self.tape_display_length) # new limit order book
        self.agg_LOB = {}
        self.agg_LOB_aft = {}

        self.next_states = {}
        self.rewards = {}
        self.dones = {}
        self.done_set = set()
        self.infos = {}

        self.trades = {} # a trade between init_party & counter_party
        self.order_in_book = {} # unfilled orders goes to LOB

        self.t_step = 0

        self.reset_traders_acc()

        return self.reset_traders_agg_LOB()

    # actions is a list of actions from all agents (traders) at t step
    # each action is a list of (ID, type, side, size, price)
    def step(self, actions):
        self.next_states, self.rewards, self.dones, self.infos = {}, {}, {}, {}
        self.agg_LOB = self.set_agg_LOB() # LOB state at t before processing LOB
        actions = self.rand_exec_seq(actions, 0) # randomized traders execution sequence
        self.do_actions(actions) # Begin processing LOB
        self.mark_to_mkt() # mark to market
        # after processing LOB
        state_input = self.prep_next_state()
        self.next_states, self.rewards, self.dones, self.infos = self.set_step_outputs(state_input)
        self.t_step += 1
        return self.next_states, self.rewards, self.dones, self.infos

    # render
    def render(self):
        print('\nLOB:\n', self.LOB)
        print('\nagg_LOB:\n', self.agg_LOB)
        print('\nagg_LOB_aft:\n', self.agg_LOB_aft)
        print('\nnext_states:\n', self.next_states)
        print('\nrewards:\n', self.rewards)
        print('\ndones:\n', self.dones)
        print('\ninfos:\n', self.infos)
        self.print_accs()
        print('total_sys_profit:', self.total_sys_profit())
        print('total_sys_nav:', self.total_sys_nav())
        return 0
