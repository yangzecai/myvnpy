"""
动量因子模块
计算价格动量相关指标
"""

import numpy as np
from typing import List, Optional


class MomentumFactor:
    """动量因子"""
    
    def __init__(self, period: int = 20):
        """
        初始化
        :param period: 动量计算周期
        """
        self.period = period
    
    def calculate(self, close_prices: np.ndarray) -> float:
        """
        计算动量因子得分
        :param close_prices: 收盘价数组
        :return: 动量得分 [-1, 1]
        """
        if len(close_prices) < self.period + 1:
            return 0.0
        
        # 计算收益率
        current_price = close_prices[-1]
        past_price = close_prices[-self.period - 1]
        
        if past_price == 0:
            return 0.0
        
        returns = (current_price - past_price) / past_price
        
        # 使用tanh将收益率映射到[-1, 1]
        score = np.tanh(returns * 10)
        
        return float(score)
    
    def calculate_roc(self, close_prices: np.ndarray, roc_period: int = 10) -> float:
        """
        计算变动率(ROC)
        :param close_prices: 收盘价数组
        :param roc_period: ROC周期
        :return: ROC值
        """
        if len(close_prices) < roc_period + 1:
            return 0.0
        
        current = close_prices[-1]
        past = close_prices[-roc_period - 1]
        
        if past == 0:
            return 0.0
        
        return (current - past) / past
    
    def calculate_momentum_rank(self, 
                               close_prices_list: List[np.ndarray]) -> List[int]:
        """
        计算动量排名
        :param close_prices_list: 多只股票收盘价列表
        :return: 排名列表（从大到小）
        """
        momentum_scores = []
        for prices in close_prices_list:
            score = self.calculate(prices)
            momentum_scores.append(score)
        
        # 返回排序后的索引（从大到小）
        return np.argsort(momentum_scores)[::-1].tolist()