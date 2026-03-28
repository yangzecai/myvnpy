"""
MACD反向策略

该策略采用反向交易逻辑：
- MACD死叉（DIF下穿DEA）时买入
- MACD金叉（DIF上穿DEA）时卖出

这种反向策略适用于震荡行情或趋势反转的场景，
与常规MACD策略形成对冲。
"""

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)


class MacdReverseStrategy(CtaTemplate):
    """
    MACD反向策略
    DIF下穿DEA（死叉）买入，DIF上穿DEA（金叉）卖出
    """

    author = "MyQuant"

    # 策略参数
    fast_period: int = 12      # 快线周期
    slow_period: int = 26      # 慢线周期
    signal_period: int = 9     # 信号周期
    fixed_size: int = 1        # 交易手数

    parameters = [
        "fast_period",
        "slow_period",
        "signal_period",
        "fixed_size"
    ]

    # 策略变量
    dif: float = 0
    dea: float = 0
    macd: float = 0
    dif_prev: float = 0       # 上一周期DIF值
    dea_prev: float = 0       # 上一周期DEA值

    variables = [
        "dif",
        "dea",
        "macd",
        "dif_prev",
        "dea_prev",
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")
        self.load_bar(10)

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")
        self.put_event()

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")
        self.put_event()

    def on_tick(self, tick: TickData):
        """Tick数据回调"""
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """K线数据回调"""
        # 撤销所有未成交委托
        self.cancel_all()

        # 更新K线到ArrayManager
        am = self.am
        am.update_bar(bar)

        # 检查是否初始化完成
        if not am.inited:
            return

        # 计算MACD指标
        dif, dea, macd = am.macd(self.fast_period, self.slow_period, self.signal_period)

        # 保存上一周期的值
        self.dif_prev = self.dif
        self.dea_prev = self.dea

        # 更新当前值
        self.dif = dif
        self.dea = dea
        self.macd = macd

        # 判断金叉和死叉
        # 金叉：上一周期DIF < DEA，当前周期DIF > DEA
        golden_cross = self.dif_prev < self.dea_prev and self.dif > self.dea
        # 死叉：上一周期DIF > DEA，当前周期DIF < DEA
        dead_cross = self.dif_prev > self.dea_prev and self.dif < self.dea

        # 获取当前持仓
        pos = self.pos

        # 反向交易逻辑：
        # - 死叉买入（预期反弹）
        # - 金叉卖出（预期回调）

        if pos == 0:
            # 无持仓时
            if dead_cross:
                # 死叉出现，反向买入（全仓）
                # 计算隔日涨停价（假设涨停幅度为10%）
                limit_up_price = bar.close_price * 1.1
                # 计算全仓股数（股票交易）
                capital = self.cta_engine.capital
                # 股票交易：可用资金除以涨停价，向下取整到100的整数倍
                max_shares = int(capital / limit_up_price) // 100 * 100
                if max_shares > 0:
                    # 股票交易通常按100股为1手，这里直接使用股数
                    self.buy(limit_up_price, max_shares)
                    self.write_log(f"死叉全仓买入 {max_shares}股 @ {limit_up_price}")

        elif pos > 0:
            # 持有多头仓位时
            if golden_cross:
                # 金叉出现，反向卖出（清仓）
                # 计算隔日跌停价（假设跌停幅度为10%）
                limit_down_price = bar.close_price * 0.9
                self.sell(limit_down_price, abs(pos))
                self.write_log(f"金叉清仓卖出 {abs(pos)}股 @ {limit_down_price}")

        self.put_event()

    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.write_log(f"成交: {trade.direction.value} {trade.volume}手 @ {trade.price}")
        self.put_event()

    def on_order(self, order: OrderData):
        """委托回调"""
        pass

    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
