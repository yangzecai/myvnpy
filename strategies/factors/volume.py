"""
成交量因子模块
计算成交量相关指标
"""

import numpy as np
from typing import Optional


class VolumeFactor:
    """成交量因子"""
    
    def __init__(self, volume_period: int = 20):
        """
        初始化
        :param volume_period: 成交量均线周期
        """
        self.volume_period = volume_period
    
    def calculate_volume_ratio(self, volumes: np.ndarray) -> float:
        """
        计算成交量比率（当前成交量/平均成交量）
        :param volumes: 成交量数组
        :return: 成交量比率
        """
        if len(volumes) < self.volume_period:
            return 1.0
        
        current_volume = volumes[-1]
        avg_volume = np.mean(volumes[-self.volume_period:])
        
        if avg_volume == 0:
            return 1.0
        
        return current_volume / avg_volume
    
    def calculate_volume_score(self, volumes: np.ndarray) -> float:
        """
        计算成交量得分
        温和放量为正面信号，过度放量或缩量为负面信号
        :param volumes: 成交量数组
        :return: 成交量得分 [-1, 1]
        """
        volume_ratio = self.calculate_volume_ratio(volumes)
        
        # 成交量评分逻辑
        if 1.0 <= volume_ratio <= 2.0:
            # 温和放量，正面信号
            score = (volume_ratio - 1.0) * 2 - 0.5  # 映射到[-0.5, 1.5]，中心在0.5
        elif volume_ratio > 2.0:
            # 过度放量，可能是顶部信号
            score = 1.0 - (volume_ratio - 2.0) * 0.5
        else:
            # 缩量，负面信号
            score = volume_ratio - 1.0  # 映射到[-1, 0]
        
        return max(-1.0, min(1.0, score))
    
    def calculate_volume_trend(self, volumes: np.ndarray) -> float:
        """
        计算成交量趋势
        :param volumes: 成交量数组
        :return: 成交量趋势得分 [-1, 1]
        """
        if len(volumes) < self.volume_period * 2:
            return 0.0
        
        # 近期成交量均值
        recent_avg = np.mean(volumes[-self.volume_period:])
        # 远期成交量均值
        past_avg = np.mean(volumes[-self.volume_period*2:-self.volume_period])
        
        if past_avg == 0:
            return 0.0
        
        # 计算变化率
        change_rate = (recent_avg - past_avg) / past_avg
        
        # 映射到[-1, 1]
        return np.tanh(change_rate * 3)