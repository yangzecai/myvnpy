"""
双均线策略示例
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


class DoubleMaStrategy(CtaTemplate):
    """
    双均线策略
    快线突破慢线买入，快线跌破慢线卖出
    """
    
    author = "MyQuant"
    
    # 策略参数
    fast_window: int = 10      # 快线周期
    slow_window: int = 20      # 慢线周期
    fixed_size: int = 1        # 交易手数
    
    parameters = [
        "fast_window",
        "slow_window",
        "fixed_size"
    ]
    
    # 策略变量
    fast_ma: float = 0
    slow_ma: float = 0
    ma_diff: float = 0
    
    variables = [
        "fast_ma",
        "slow_ma",
        "ma_diff"
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
        
        # 计算均线
        self.fast_ma = am.sma(self.fast_window)
        self.slow_ma = am.sma(self.slow_window)
        self.ma_diff = self.fast_ma - self.slow_ma
        
        # 获取当前持仓
        pos = self.pos
        
        # 交易逻辑
        if pos == 0:
            if self.fast_ma > self.slow_ma:
                # 金叉，买入
                self.buy(bar.close_price + 5, self.fixed_size)
        
        elif pos > 0:
            if self.fast_ma < self.slow_ma:
                # 死叉，卖出
                self.sell(bar.close_price - 5, abs(pos))
    
    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.write_log(f"成交: {trade.direction.value} {trade.volume}手 @ {trade.price}")
    
    def on_order(self, order: OrderData):
        """委托回调"""
        pass
    
    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
