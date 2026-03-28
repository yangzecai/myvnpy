"""
多因子策略

该策略综合多个技术指标因子，通过加权评分系统生成交易信号：
1. 动量因子：价格相对于N周期前的变化率
2. 波动率因子：ATR（平均真实波幅）用于衡量波动性
3. 趋势因子：使用EMA和SMA的金叉/死叉判断趋势
4. 成交量因子：成交量与均线的比值判断量能
5. RSI因子：相对强弱指标判断超买超卖

交易逻辑：
- 当综合评分超过买入阈值时，全仓买入
- 当综合评分低于卖出阈值时，清仓卖出
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


class MultiFactorStrategy(CtaTemplate):
    """
    多因子策略
    综合动量、波动率、趋势、成交量、RSI五个因子进行交易决策
    """

    author = "MyQuant"

    # 策略参数
    # K线周期参数
    momentum_period: int = 20       # 动量计算周期
    atr_period: int = 14            # ATR计算周期
    ema_fast: int = 12              # 快速EMA周期
    ema_slow: int = 26              # 慢速EMA周期
    volume_period: int = 20         # 成交量均线周期
    rsi_period: int = 14            # RSI计算周期

    # 阈值参数
    buy_threshold: float = 0.6      # 买入阈值（综合评分高于此值买入）
    sell_threshold: float = -0.6    # 卖出阈值（综合评分低于此值卖出）

    # 权重参数（各因子权重，总和应为1）
    momentum_weight: float = 0.25   # 动量因子权重
    volatility_weight: float = 0.15 # 波动率因子权重
    trend_weight: float = 0.30      # 趋势因子权重
    volume_weight: float = 0.15     # 成交量因子权重
    rsi_weight: float = 0.15        # RSI因子权重

    # 风险控制参数
    atr_multiplier: float = 2.0     # ATR倍数用于止损
    max_position_pct: float = 0.95  # 最大仓位比例（相对于资金）

    parameters = [
        "momentum_period",
        "atr_period",
        "ema_fast",
        "ema_slow",
        "volume_period",
        "rsi_period",
        "buy_threshold",
        "sell_threshold",
        "momentum_weight",
        "volatility_weight",
        "trend_weight",
        "volume_weight",
        "rsi_weight",
        "atr_multiplier",
        "max_position_pct",
    ]

    # 策略变量
    composite_score: float = 0.0    # 综合评分
    momentum_score: float = 0.0     # 动量因子得分
    volatility_score: float = 0.0   # 波动率因子得分
    trend_score: float = 0.0        # 趋势因子得分
    volume_score: float = 0.0       # 成交量因子得分
    rsi_score: float = 0.0          # RSI因子得分

    atr_value: float = 0.0          # ATR值
    stop_loss_price: float = 0.0    # 止损价格

    variables = [
        "composite_score",
        "momentum_score",
        "volatility_score",
        "trend_score",
        "volume_score",
        "rsi_score",
        "atr_value",
        "stop_loss_price",
    ]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")
        # 加载历史数据用于计算指标
        # 需要足够的数据来计算所有指标
        required_days = max(
            self.momentum_period,
            self.atr_period,
            self.ema_slow,
            self.volume_period,
            self.rsi_period
        ) + 10
        self.load_bar(required_days)

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """Tick数据回调"""
        self.bg.update_tick(tick)

    def calculate_momentum_factor(self, am: ArrayManager) -> float:
        """
        计算动量因子得分
        基于价格变化率，归一化到[-1, 1]区间
        """
        if len(am.close_array) < self.momentum_period + 1:
            return 0.0

        # 计算价格变化率
        current_price = am.close_array[-1]
        past_price = am.close_array[-self.momentum_period - 1]

        if past_price == 0:
            return 0.0

        # 计算收益率
        returns = (current_price - past_price) / past_price

        # 将收益率映射到[-1, 1]区间，使用tanh进行压缩
        import math
        score = math.tanh(returns * 10)  # 乘以10增加敏感度

        return score

    def calculate_volatility_factor(self, am: ArrayManager) -> float:
        """
        计算波动率因子得分
        基于ATR，波动率越低得分越高（倾向于低波动环境）
        """
        if not am.inited or len(am.close_array) < self.atr_period:
            return 0.0

        # 计算ATR
        atr = am.atr(self.atr_period)

        if atr is None or atr == 0:
            return 0.0

        self.atr_value = atr

        # 计算ATR与价格的比率（归一化波动率）
        current_price = am.close_array[-1]
        volatility_ratio = atr / current_price

        # 波动率越低得分越高（低波动时更容易有趋势）
        # 假设正常波动率在0.01-0.05之间
        import math
        if volatility_ratio < 0.01:
            score = 1.0
        elif volatility_ratio > 0.05:
            score = -1.0
        else:
            # 线性映射
            score = 1.0 - (volatility_ratio - 0.01) / (0.05 - 0.01) * 2

        return max(-1.0, min(1.0, score))

    def calculate_trend_factor(self, am: ArrayManager) -> float:
        """
        计算趋势因子得分
        基于EMA金叉/死叉和趋势强度
        """
        if not am.inited or len(am.close_array) < self.ema_slow:
            return 0.0

        # 计算EMA
        ema_fast_value = am.ema(self.ema_fast)
        ema_slow_value = am.ema(self.ema_slow)

        if ema_fast_value is None or ema_slow_value is None:
            return 0.0

        # 计算EMA差值比例
        if ema_slow_value == 0:
            return 0.0

        ema_diff_pct = (ema_fast_value - ema_slow_value) / ema_slow_value

        # 映射到[-1, 1]区间
        import math
        score = math.tanh(ema_diff_pct * 50)  # 乘以50增加敏感度

        return score

    def calculate_volume_factor(self, am: ArrayManager) -> float:
        """
        计算成交量因子得分
        基于成交量与均线的比值
        """
        if len(am.volume_array) < self.volume_period:
            return 0.0

        # 计算成交量均线
        volume_ma = sum(am.volume_array[-self.volume_period:]) / self.volume_period
        current_volume = am.volume_array[-1]

        if volume_ma == 0:
            return 0.0

        # 计算成交量比率
        volume_ratio = current_volume / volume_ma

        # 成交量温和放大为正面信号，过度放量或缩量为负面信号
        if 1.0 <= volume_ratio <= 2.0:
            # 温和放量，正面信号
            score = (volume_ratio - 1.0) * 2  # 映射到[0, 2]
        elif volume_ratio > 2.0:
            # 过度放量，可能是顶部信号
            score = 1.0 - (volume_ratio - 2.0) * 0.5
        else:
            # 缩量，负面信号
            score = volume_ratio - 1.0  # 映射到[-1, 0]

        return max(-1.0, min(1.0, score))

    def calculate_rsi_factor(self, am: ArrayManager) -> float:
        """
        计算RSI因子得分
        基于RSI指标，超买超卖判断
        """
        if not am.inited or len(am.close_array) < self.rsi_period + 1:
            return 0.0

        # 计算RSI
        rsi = am.rsi(self.rsi_period)

        if rsi is None:
            return 0.0

        # RSI映射到[-1, 1]区间
        # RSI < 30: 超卖，买入信号 (得分接近1)
        # RSI > 70: 超买，卖出信号 (得分接近-1)
        # RSI = 50: 中性 (得分接近0)
        if rsi < 30:
            score = 1.0
        elif rsi > 70:
            score = -1.0
        else:
            # 线性映射
            score = (50 - rsi) / 20

        return max(-1.0, min(1.0, score))

    def calculate_composite_score(self, am: ArrayManager) -> float:
        """
        计算综合评分
        加权平均各因子得分
        """
        self.momentum_score = self.calculate_momentum_factor(am)
        self.volatility_score = self.calculate_volatility_factor(am)
        self.trend_score = self.calculate_trend_factor(am)
        self.volume_score = self.calculate_volume_factor(am)
        self.rsi_score = self.calculate_rsi_factor(am)

        # 加权计算综合评分
        composite = (
            self.momentum_score * self.momentum_weight +
            self.volatility_score * self.volatility_weight +
            self.trend_score * self.trend_weight +
            self.volume_score * self.volume_weight +
            self.rsi_score * self.rsi_weight
        )

        return composite

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

        # 计算综合评分
        self.composite_score = self.calculate_composite_score(am)

        # 获取当前持仓
        pos = self.pos

        # 计算止损价格（基于ATR）
        if self.atr_value > 0 and pos > 0:
            self.stop_loss_price = bar.close_price - self.atr_multiplier * self.atr_value

        # 交易逻辑
        if pos == 0:
            # 无持仓时，根据综合评分决定买入
            if self.composite_score > self.buy_threshold:
                # 买入信号
                # 计算隔日涨停价（假设涨停幅度为10%）
                limit_up_price = bar.close_price * 1.1

                # 计算可用资金
                capital = self.cta_engine.capital
                max_invest = capital * self.max_position_pct

                # 股票交易：可用资金除以涨停价，向下取整到100的整数倍
                max_shares = int(max_invest / limit_up_price) // 100 * 100

                if max_shares > 0:
                    self.buy(limit_up_price, max_shares)
                    self.write_log(
                        f"买入信号触发 - 综合评分: {self.composite_score:.4f}, "
                        f"动量: {self.momentum_score:.4f}, 波动率: {self.volatility_score:.4f}, "
                        f"趋势: {self.trend_score:.4f}, 成交量: {self.volume_score:.4f}, "
                        f"RSI: {self.rsi_score:.4f}"
                    )

        elif pos > 0:
            # 有持仓时，根据综合评分或止损决定卖出
            should_sell = False
            sell_reason = ""

            # 条件1：综合评分低于卖出阈值
            if self.composite_score < self.sell_threshold:
                should_sell = True
                sell_reason = f"评分低于阈值({self.composite_score:.4f} < {self.sell_threshold})"

            # 条件2：触发ATR止损
            elif bar.close_price < self.stop_loss_price:
                should_sell = True
                sell_reason = f"触发止损({bar.close_price:.2f} < {self.stop_loss_price:.2f})"

            if should_sell:
                # 卖出信号
                limit_down_price = bar.close_price * 0.9
                self.sell(limit_down_price, abs(pos))
                self.write_log(
                    f"卖出信号触发 - 原因: {sell_reason}, "
                    f"综合评分: {self.composite_score:.4f}"
                )

        # 更新UI
        self.put_event()

    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.write_log(f"成交: {trade.direction.value} {trade.volume}手 @ {trade.price}")

        # 更新止损价格
        if trade.direction.value == "多" and trade.offset.value == "开":
            self.stop_loss_price = trade.price - self.atr_multiplier * self.atr_value

    def on_order(self, order: OrderData):
        """委托回调"""
        self.write_log(f"委托: {order.direction.value} {order.volume}手 @ {order.price}")

    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass
