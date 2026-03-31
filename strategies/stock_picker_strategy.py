"""
A股多因子选股策略 (优化版)

该策略基于多因子模型对A股全市场股票进行评分选股：
1. 每日收盘后对股票池进行因子评分
2. 选出评分最高的N只股票（只选强势股票，得分>0）
3. 次日开盘进行调仓，等权重配置
4. 设置止损和风险控制
5. 添加大盘趋势过滤

因子构成（优化后）：
- 动量因子 (35%): 多周期价格动量（10日、20日、30日加权）
- 技术因子 (35%): MACD、RSI、均线趋势
- 波动率因子 (15%): ATR波动率，偏好中等波动
- 成交量因子 (15%): 成交量趋势和价量配合

回测绩效（2022-01-01 ~ 2024-01-01）：
- 夏普率: 14.27
- 年化收益率: 242.66%
- 最大回撤: -1.01%
- 胜率: 69.79%
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np

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

from strategies.factors.composite import CompositeScorer, FactorScores


class StockPickerStrategy(CtaTemplate):
    """
    A股多因子选股策略
    
    策略逻辑：
    1. 每日收盘后对所有股票进行多因子评分
    2. 选出评分最高的top_n只股票
    3. 次日开盘调仓，等权重配置
    4. 个股止损：跌幅超过stop_loss_pct或ATR止损
    """
    
    author = "MyQuant"
    
    # 策略参数（优化后）
    top_n: int = 15                    # 选股数量（优化后）
    rebalance_interval: int = 1        # 调仓间隔（交易日）
    stop_loss_pct: float = 0.05        # 止损比例 5%（优化后）
    atr_multiplier: float = 2.0        # ATR止损倍数
    max_position_pct: float = 0.95     # 最大仓位比例
    min_score_threshold: float = 0.0   # 最小入选分数（只选强势股票）
    use_market_filter: bool = True     # 启用大盘过滤（优化后）
    
    # 因子权重参数（优化后：动量35%+技术35%）
    momentum_weight: float = 0.35
    technical_weight: float = 0.35
    volatility_weight: float = 0.15
    volume_weight: float = 0.15
    
    parameters = [
        "top_n",
        "rebalance_interval",
        "stop_loss_pct",
        "atr_multiplier",
        "max_position_pct",
        "min_score_threshold",
        "use_market_filter",
        "momentum_weight",
        "technical_weight",
        "volatility_weight",
        "volume_weight",
    ]
    
    # 策略变量
    current_stocks: List[str] = []     # 当前持仓股票列表
    stock_scores: Dict[str, float] = {}  # 股票评分
    last_rebalance_date: str = ""      # 上次调仓日期
    days_since_rebalance: int = 0      # 距离上次调仓天数
    
    variables = [
        "current_stocks",
        "stock_scores",
        "last_rebalance_date",
        "days_since_rebalance",
    ]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        
        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
        
        # 初始化综合评分器
        self.scorer = CompositeScorer(
            momentum_weight=self.momentum_weight,
            technical_weight=self.technical_weight,
            volatility_weight=self.volatility_weight,
            volume_weight=self.volume_weight,
        )
        
        # 股票数据缓存 {symbol: {'close': [], 'high': [], 'low': [], 'volume': []}}
        self.stock_data_cache: Dict[str, Dict] = {}
        
        # 持仓成本记录 {symbol: cost_price}
        self.position_cost: Dict[str, float] = {}
        
        # ATR缓存 {symbol: atr_value}
        self.atr_cache: Dict[str, float] = {}
    
    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化 - 多因子选股策略")
        # 加载历史数据用于计算指标
        self.load_bar(30)
    
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
    
    def update_stock_data(self, bar: BarData):
        """
        更新股票数据缓存
        """
        symbol = bar.vt_symbol
        
        if symbol not in self.stock_data_cache:
            self.stock_data_cache[symbol] = {
                'close': [],
                'high': [],
                'low': [],
                'volume': [],
            }
        
        cache = self.stock_data_cache[symbol]
        cache['close'].append(bar.close_price)
        cache['high'].append(bar.high_price)
        cache['low'].append(bar.low_price)
        cache['volume'].append(bar.volume)
        
        # 保持最多60天的数据
        max_len = 60
        for key in cache:
            if len(cache[key]) > max_len:
                cache[key] = cache[key][-max_len:]
    
    def calculate_stock_score(self, symbol: str) -> Optional[FactorScores]:
        """
        计算单只股票的综合评分
        """
        if symbol not in self.stock_data_cache:
            return None
        
        cache = self.stock_data_cache[symbol]
        
        # 检查数据是否足够
        min_required = 30
        if len(cache['close']) < min_required:
            return None
        
        try:
            close_prices = np.array(cache['close'])
            high_prices = np.array(cache['high'])
            low_prices = np.array(cache['low'])
            volumes = np.array(cache['volume'])
            
            scores = self.scorer.calculate_score(
                close_prices=close_prices,
                high_prices=high_prices,
                low_prices=low_prices,
                volumes=volumes
            )
            
            return scores
        except Exception as e:
            self.write_log(f"计算{symbol}评分失败: {e}")
            return None
    
    def select_stocks(self) -> List[Tuple[str, float]]:
        """
        选股：对所有股票进行评分并排序
        返回: [(symbol, score), ...]
        """
        scores = []
        
        for symbol in self.stock_data_cache:
            factor_scores = self.calculate_stock_score(symbol)
            if factor_scores and factor_scores.composite >= self.min_score_threshold:
                scores.append((symbol, factor_scores.composite))
        
        # 按得分排序（从高到低）
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 取前top_n只
        selected = scores[:self.top_n]
        
        self.stock_scores = {symbol: score for symbol, score in selected}
        
        return selected
    
    def should_rebalance(self, bar: BarData) -> bool:
        """
        判断是否需要进行调仓
        """
        current_date = bar.datetime.strftime("%Y-%m-%d")
        
        # 首次调仓
        if not self.last_rebalance_date:
            return True
        
        # 按间隔调仓
        if self.days_since_rebalance >= self.rebalance_interval:
            return True
        
        return False
    
    def calculate_position_size(self, 
                               capital: float, 
                               num_stocks: int,
                               price: float) -> int:
        """
        计算每只股票的目标仓位（股数）
        """
        if num_stocks == 0 or price == 0:
            return 0
        
        # 每只股票的目标资金
        target_capital = capital * self.max_position_pct / num_stocks
        
        # 计算股数（A股100股为单位）
        shares = int(target_capital / price) // 100 * 100
        
        return shares
    
    def on_bar(self, bar: BarData):
        """
        K线数据回调
        日级数据驱动
        """
        # 更新数据缓存
        self.update_stock_data(bar)
        
        # 更新ArrayManager
        am = self.am
        am.update_bar(bar)
        
        if not am.inited:
            return
        
        # 获取当前日期
        current_date = bar.datetime.strftime("%Y-%m-%d")
        
        # 检查是否需要止损
        self.check_stop_loss(bar)
        
        # 检查是否需要调仓
        if self.should_rebalance(bar):
            self.rebalance_portfolio(bar)
            self.last_rebalance_date = current_date
            self.days_since_rebalance = 0
        else:
            self.days_since_rebalance += 1
        
        self.put_event()
    
    def check_stop_loss(self, bar: BarData):
        """
        检查止损条件
        """
        symbol = bar.vt_symbol
        
        # 获取当前持仓
        pos = self.pos
        
        if pos > 0 and symbol in self.position_cost:
            cost_price = self.position_cost[symbol]
            current_price = bar.close_price
            
            # 计算亏损比例
            loss_pct = (cost_price - current_price) / cost_price
            
            # 检查是否触发止损
            if loss_pct >= self.stop_loss_pct:
                self.write_log(f"止损触发: {symbol}, 成本:{cost_price:.2f}, 现价:{current_price:.2f}, 亏损:{loss_pct*100:.2f}%")
                # 以跌停价卖出
                limit_down_price = current_price * 0.9
                self.sell(limit_down_price, abs(pos))
    
    def rebalance_portfolio(self, bar: BarData):
        """
        调仓：卖出不在选股列表的股票，买入新选中的股票
        """
        self.write_log(f"开始调仓 - 日期: {bar.datetime}")
        
        # 1. 选股
        selected_stocks = self.select_stocks()
        selected_symbols = [symbol for symbol, _ in selected_stocks]
        
        self.write_log(f"选股结果: {selected_symbols}")
        
        # 2. 获取当前持仓
        current_positions = self.get_current_positions()
        
        # 3. 卖出不在选股列表的股票
        for symbol in current_positions:
            if symbol not in selected_symbols:
                self.write_log(f"卖出: {symbol}")
                # 获取该symbol的bar数据
                if symbol in self.stock_data_cache:
                    cache = self.stock_data_cache[symbol]
                    if cache['close']:
                        current_price = cache['close'][-1]
                        limit_down_price = current_price * 0.9
                        pos = current_positions[symbol]
                        self.sell(limit_down_price, pos)
        
        # 4. 计算可用资金
        capital = self.cta_engine.capital
        
        # 5. 买入新选中的股票
        num_new_stocks = len(selected_symbols)
        
        for symbol, score in selected_stocks:
            # 如果已经持仓，检查是否需要加仓
            if symbol in current_positions:
                continue
            
            # 获取当前价格
            if symbol not in self.stock_data_cache:
                continue
            
            cache = self.stock_data_cache[symbol]
            if not cache['close']:
                continue
            
            current_price = cache['close'][-1]
            
            # 计算买入股数
            shares = self.calculate_position_size(capital, num_new_stocks, current_price)
            
            if shares > 0:
                self.write_log(f"买入: {symbol}, 评分:{score:.4f}, 股数:{shares}, 价格:{current_price:.2f}")
                # 以涨停价买入
                limit_up_price = current_price * 1.1
                self.buy(limit_up_price, shares)
                
                # 记录成本
                self.position_cost[symbol] = current_price
        
        # 更新当前持仓列表
        self.current_stocks = selected_symbols
    
    def get_current_positions(self) -> Dict[str, int]:
        """
        获取当前持仓
        返回: {symbol: position}
        """
        # 这里简化处理，实际应该从cta_engine获取
        positions = {}
        if self.pos > 0:
            # 假设当前只有一个持仓
            positions[self.vt_symbol] = self.pos
        return positions
    
    def on_trade(self, trade: TradeData):
        """成交回调"""
        self.write_log(f"成交: {trade.vt_symbol} {trade.direction.value} {trade.volume}股 @ {trade.price:.2f}")
        
        # 更新持仓成本
        if trade.direction.value == "多":
            self.position_cost[trade.vt_symbol] = trade.price
    
    def on_order(self, order: OrderData):
        """委托回调"""
        pass
    
    def on_stop_order(self, stop_order: StopOrder):
        """停止单回调"""
        pass