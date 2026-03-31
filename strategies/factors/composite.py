"""
综合评分模块
整合多个因子计算综合评分
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .momentum import MomentumFactor
from .technical import TechnicalFactor
from .volatility import VolatilityFactor
from .volume import VolumeFactor


@dataclass
class FactorScores:
    """因子得分数据类"""
    momentum: float = 0.0
    technical: float = 0.0
    volatility: float = 0.0
    volume: float = 0.0
    composite: float = 0.0


class CompositeScorer:
    """综合评分器"""
    
    def __init__(self,
                 momentum_weight: float = 0.25,
                 technical_weight: float = 0.30,
                 volatility_weight: float = 0.20,
                 volume_weight: float = 0.25):
        """
        初始化
        :param momentum_weight: 动量因子权重
        :param technical_weight: 技术因子权重
        :param volatility_weight: 波动率因子权重
        :param volume_weight: 成交量因子权重
        """
        # 归一化权重
        total = momentum_weight + technical_weight + volatility_weight + volume_weight
        self.momentum_weight = momentum_weight / total
        self.technical_weight = technical_weight / total
        self.volatility_weight = volatility_weight / total
        self.volume_weight = volume_weight / total
        
        # 初始化各因子计算器
        self.momentum_factor = MomentumFactor(period=20)
        self.technical_factor = TechnicalFactor()
        self.volatility_factor = VolatilityFactor()
        self.volume_factor = VolumeFactor()
    
    def calculate_score(self,
                       close_prices: np.ndarray,
                       high_prices: np.ndarray,
                       low_prices: np.ndarray,
                       volumes: np.ndarray) -> FactorScores:
        """
        计算综合评分
        :param close_prices: 收盘价数组
        :param high_prices: 最高价数组
        :param low_prices: 最低价数组
        :param volumes: 成交量数组
        :return: 因子得分
        """
        # 计算各因子得分
        momentum_score = self.momentum_factor.calculate(close_prices)
        
        # 技术因子取MACD和RSI的平均
        macd_score = self.technical_factor.calculate_macd_score(close_prices)
        rsi_score = self.technical_factor.calculate_rsi_score(close_prices)
        ma_score = self.technical_factor.calculate_ma_trend(close_prices)
        technical_score = (macd_score + rsi_score + ma_score) / 3
        
        volatility_score = self.volatility_factor.calculate_volatility_score(
            high_prices, low_prices, close_prices
        )
        
        volume_score = self.volume_factor.calculate_volume_score(volumes)
        
        # 计算综合得分
        composite = (
            momentum_score * self.momentum_weight +
            technical_score * self.technical_weight +
            volatility_score * self.volatility_weight +
            volume_score * self.volume_weight
        )
        
        return FactorScores(
            momentum=momentum_score,
            technical=technical_score,
            volatility=volatility_score,
            volume=volume_score,
            composite=composite
        )
    
    def rank_stocks(self,
                   stock_data: Dict[str, Dict],
                   top_n: int = 20) -> List[Tuple[str, float]]:
        """
        对股票进行排名
        :param stock_data: 股票数据字典 {symbol: {close, high, low, volume}}
        :param top_n: 返回前N名
        :return: [(symbol, score), ...]
        """
        scores = []
        
        for symbol, data in stock_data.items():
            try:
                factor_scores = self.calculate_score(
                    close_prices=data['close'],
                    high_prices=data['high'],
                    low_prices=data['low'],
                    volumes=data['volume']
                )
                scores.append((symbol, factor_scores.composite))
            except Exception as e:
                continue
        
        # 按得分排序（从高到低）
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_n]
    
    def get_factor_weights(self) -> Dict[str, float]:
        """获取当前因子权重"""
        return {
            'momentum': self.momentum_weight,
            'technical': self.technical_weight,
            'volatility': self.volatility_weight,
            'volume': self.volume_weight,
        }