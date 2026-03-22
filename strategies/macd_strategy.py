"""
MACD策略示例
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


class MacdStrategy(CtaTemplate):
    """
    MACD策略
    DIF上穿DEA（金叉）买入，DIF下穿DEA（死叉）卖出
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
    
    variables = [
        "dif",
        "dea",
        "macd"
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
    
    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")
    
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
        self.dif = dif
        self.dea = dea
        self.macd = macd
        
        # 获取当前持仓
        pos = self.pos
        
        # 交易逻辑
        if pos == 0:
            # 水上金叉：DIF > DEA 且 DIF > 0 且 DEA > 0
            if dif > dea and dif > 0 and dea > 0:
                # 水上金叉，买入
                # 计算隔日涨停价（假设涨停幅度为10%）
                limit_up_price = bar.close_price * 1.1
                # 计算全仓股数（股票交易）
                capital = self.cta_engine.capital
                # 股票交易：可用资金除以涨停价，向下取整到100的整数倍
                max_shares = int(capital / limit_up_price) // 100 * 100
                if max_shares > 0:
                    # 股票交易通常按100股为1手，这里直接使用股数
                    self.buy(limit_up_price, max_shares)
        
        elif pos > 0:
            # 死叉：DIF < DEA
            if dif < dea:
                # 死叉，卖出
                # 计算隔日跌停价（假设跌停幅度为10%）
                limit_down_price = bar.close_price * 0.9
                self.sell(limit_down_price, abs(pos))
    
    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.write_log(f"成交: {trade.direction.value} {trade.volume}手 @ {trade.price}")
    
    def on_order(self, order: OrderData):
        """委托回调"""
        self.write_log(f"委托: {order.direction.value} {order.volume}手 @ {order.price}")
    
    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
