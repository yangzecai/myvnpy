"""
技术因子模块
计算技术指标相关因子
"""

import numpy as np
from typing import Optional, Tuple


class TechnicalFactor:
    """技术因子"""
    
    def __init__(self, 
                 fast_period: int = 12,
                 slow_period: int = 26,
                 signal_period: int = 9,
                 rsi_period: int = 14):
        """
        初始化
        :param fast_period: MACD快线周期
        :param slow_period: MACD慢线周期
        :param signal_period: MACD信号周期
        :param rsi_period: RSI周期
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.rsi_period = rsi_period
    
    def calculate_macd(self, close_prices: np.ndarray) -> Tuple[float, float, float]:
        """
        计算MACD指标
        :param close_prices: 收盘价数组
        :return: (DIF, DEA, MACD)
        """
        if len(close_prices) < self.slow_period + self.signal_period:
            return 0.0, 0.0, 0.0
        
        # 计算EMA
        ema_fast = self._calculate_ema(close_prices, self.fast_period)
        ema_slow = self._calculate_ema(close_prices, self.slow_period)
        
        # 计算DIF
        dif = ema_fast - ema_slow
        
        # 计算DEA (DIF的EMA)
        dea = self._calculate_ema(np.array([dif]), self.signal_period)
        
        # 计算MACD柱状图
        macd = (dif - dea) * 2
        
        return dif, dea, macd
    
    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """计算EMA"""
        if len(prices) < period:
            return prices[-1] if len(prices) > 0 else 0.0
        
        # 使用pandas风格的EMA计算
        alpha = 2 / (period + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return ema
    
    def calculate_rsi(self, close_prices: np.ndarray) -> float:
        """
        计算RSI指标
        :param close_prices: 收盘价数组
        :return: RSI值 [0, 100]
        """
        if len(close_prices) < self.rsi_period + 1:
            return 50.0
        
        # 计算价格变化
        deltas = np.diff(close_prices)
        
        # 分离上涨和下跌
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # 计算平均上涨和下跌
        avg_gain = np.mean(gains[-self.rsi_period:])
        avg_loss = np.mean(losses[-self.rsi_period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_ma_trend(self, 
                          close_prices: np.ndarray,
                          short_period: int = 5,
                          medium_period: int = 10,
                          long_period: int = 20) -> float:
        """
        计算均线趋势得分
        :param close_prices: 收盘价数组
        :param short_period: 短期均线周期
        :param medium_period: 中期均线周期
        :param long_period: 长期均线周期
        :return: 趋势得分 [-1, 1]
        """
        if len(close_prices) < long_period:
            return 0.0
        
        # 计算各周期均线
        ma_short = np.mean(close_prices[-short_period:])
        ma_medium = np.mean(close_prices[-medium_period:])
        ma_long = np.mean(close_prices[-long_period:])
        
        # 多头排列得分
        if ma_short > ma_medium > ma_long:
            # 多头排列，计算强度
            strength = (ma_short - ma_long) / ma_long
            return min(1.0, strength * 10)
        elif ma_short < ma_medium < ma_long:
            # 空头排列
            strength = (ma_long - ma_short) / ma_long
            return max(-1.0, -strength * 10)
        else:
            # 震荡
            return 0.0
    
    def calculate_macd_score(self, close_prices: np.ndarray) -> float:
        """
        计算MACD得分
        :param close_prices: 收盘价数组
        :return: MACD得分 [-1, 1]
        """
        dif, dea, macd = self.calculate_macd(close_prices)
        
        # DIF > DEA 且都在零轴上方为强势
        if dif > dea and dif > 0:
            return min(1.0, (dif - dea) / abs(dea) if dea != 0 else 0.5)
        # DIF < DEA 且都在零轴下方为弱势
        elif dif < dea and dif < 0:
            return max(-1.0, (dif - dea) / abs(dea) if dea != 0 else -0.5)
        else:
            return 0.0
    
    def calculate_rsi_score(self, close_prices: np.ndarray) -> float:
        """
        计算RSI得分
        :param close_prices: 收盘价数组
        :return: RSI得分 [-1, 1]
        """
        rsi = self.calculate_rsi(close_prices)
        
        # RSI < 30: 超卖，买入信号
        # RSI > 70: 超买，卖出信号
        # 映射到[-1, 1]
        if rsi < 30:
            return 1.0
        elif rsi > 70:
            return -1.0
        else:
            # 线性映射
            return (50 - rsi) / 20