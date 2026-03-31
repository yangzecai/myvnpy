"""
波动率因子模块
计算波动率相关指标
"""

import numpy as np
from typing import Optional


class VolatilityFactor:
    """波动率因子"""
    
    def __init__(self, atr_period: int = 14):
        """
        初始化
        :param atr_period: ATR计算周期
        """
        self.atr_period = atr_period
    
    def calculate_atr(self, 
                     high_prices: np.ndarray,
                     low_prices: np.ndarray,
                     close_prices: np.ndarray) -> float:
        """
        计算ATR (Average True Range)
        :param high_prices: 最高价数组
        :param low_prices: 最低价数组
        :param close_prices: 收盘价数组
        :return: ATR值
        """
        if len(close_prices) < self.atr_period + 1:
            return 0.0
        
        # 计算真实波幅(TR)
        tr_list = []
        for i in range(1, len(close_prices)):
            tr1 = high_prices[i] - low_prices[i]
            tr2 = abs(high_prices[i] - close_prices[i-1])
            tr3 = abs(low_prices[i] - close_prices[i-1])
            tr = max(tr1, tr2, tr3)
            tr_list.append(tr)
        
        tr_array = np.array(tr_list)
        
        # 计算ATR
        atr = np.mean(tr_array[-self.atr_period:])
        
        return atr
    
    def calculate_volatility_score(self,
                                   high_prices: np.ndarray,
                                   low_prices: np.ndarray,
                                   close_prices: np.ndarray) -> float:
        """
        计算波动率得分
        低波动率得高分（偏好低波动）
        :param high_prices: 最高价数组
        :param low_prices: 最低价数组
        :param close_prices: 收盘价数组
        :return: 波动率得分 [-1, 1]
        """
        atr = self.calculate_atr(high_prices, low_prices, close_prices)
        
        if atr == 0 or close_prices[-1] == 0:
            return 0.0
        
        # 计算ATR/价格比率
        volatility_ratio = atr / close_prices[-1]
        
        # 波动率越低得分越高
        # 假设正常波动率在0.01-0.05之间
        if volatility_ratio < 0.01:
            score = 1.0
        elif volatility_ratio > 0.05:
            score = -1.0
        else:
            # 线性映射
            score = 1.0 - (volatility_ratio - 0.01) / (0.05 - 0.01) * 2
        
        return max(-1.0, min(1.0, score))
    
    def calculate_std_score(self, close_prices: np.ndarray, period: int = 20) -> float:
        """
        基于标准差的波动率得分
        :param close_prices: 收盘价数组
        :param period: 计算周期
        :return: 波动率得分 [-1, 1]
        """
        if len(close_prices) < period:
            return 0.0
        
        # 计算收益率
        returns = np.diff(close_prices[-period:]) / close_prices[-period:-1]
        
        # 计算标准差
        std = np.std(returns)
        
        # 标准差越小越好（低波动）
        # 假设正常日波动标准差在0.01-0.03之间
        if std < 0.01:
            score = 1.0
        elif std > 0.03:
            score = -1.0
        else:
            score = 1.0 - (std - 0.01) / (0.03 - 0.01) * 2
        
        return max(-1.0, min(1.0, score))