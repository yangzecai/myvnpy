#!/usr/bin/env python
"""
新因子挖掘与验证
基于A股市场特点，实现和验证新的有效因子
"""

import os
import sys
import json
import math
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factor_analysis import DatabaseManager, load_db_config


class NewFactors:
    """新因子集合"""
    
    @staticmethod
    def calculate_value_score(close_prices: List[float], volumes: List[float]) -> float:
        """
        价值因子 - 基于价格/成交量比
        逻辑：低价格/成交量比可能意味着被低估
        """
        if len(close_prices) < 20 or len(volumes) < 20:
            return 0
        
        avg_price = sum(close_prices[-20:]) / 20
        avg_volume = sum(volumes[-20:]) / 20
        
        if avg_volume == 0:
            return 0
        
        # 价格/成交量比
        pv_ratio = avg_price / avg_volume
        
        # 比率越低，得分越高（被低估）
        if pv_ratio < 0.01:
            return 1.0
        elif pv_ratio > 0.05:
            return -1.0
        else:
            return 1.0 - (pv_ratio - 0.01) / 0.04 * 2
    
    @staticmethod
    def calculate_quality_score(close_prices: List[float]) -> float:
        """
        质量因子 - 基于收益分布的偏度
        逻辑：正偏度表示有更多正向收益，质量更好
        """
        if len(close_prices) < 60:
            return 0
        
        # 计算日收益率
        returns = [(close_prices[i] - close_prices[i-1]) / close_prices[i-1] 
                   for i in range(1, len(close_prices))]
        
        recent_returns = returns[-60:]
        
        # 计算偏度
        mean_return = sum(recent_returns) / len(recent_returns)
        variance = sum((r - mean_return) ** 2 for r in recent_returns) / len(recent_returns)
        std = math.sqrt(variance)
        
        if std == 0:
            return 0
        
        skewness = sum((r - mean_return) ** 3 for r in recent_returns) / (len(recent_returns) * std ** 3)
        
        # 正偏度得分高
        if skewness > 0.5:
            return 1.0
        elif skewness < -0.5:
            return -1.0
        else:
            return skewness * 2
    
    @staticmethod
    def calculate_liquidity_score(volumes: List[float], close_prices: List[float]) -> float:
        """
        流动性因子 - 基于Amihud非流动性指标
        逻辑：适度流动性的股票有流动性溢价
        """
        if len(volumes) < 20 or len(close_prices) < 20:
            return 0
        
        # 计算Amihud非流动性指标
        illiquidity = 0
        count = 0
        for i in range(max(1, len(close_prices)-20), len(close_prices)):
            if volumes[i] > 0:
                daily_return = abs(close_prices[i] - close_prices[i-1]) / close_prices[i-1]
                illiquidity += daily_return / volumes[i]
                count += 1
        
        if count == 0:
            return 0
        
        avg_illiquidity = illiquidity / count
        
        # 非流动性适中最好
        if 1e-6 <= avg_illiquidity <= 1e-4:
            return 1.0
        elif avg_illiquidity < 1e-7 or avg_illiquidity > 1e-3:
            return -1.0
        else:
            return 0.5
    
    @staticmethod
    def calculate_consistency_score(close_prices: List[float]) -> float:
        """
        一致性因子 - 基于收益率的一致性
        逻辑：收益稳定的股票风险更低
        """
        if len(close_prices) < 20:
            return 0
        
        # 计算日收益率
        returns = [(close_prices[i] - close_prices[i-1]) / close_prices[i-1] 
                   for i in range(1, len(close_prices))]
        
        recent_returns = returns[-20:]
        
        # 计算连续正收益天数占比
        positive_days = sum(1 for r in recent_returns if r > 0)
        positive_ratio = positive_days / len(recent_returns)
        
        # 正收益天数越多，得分越高
        if positive_ratio > 0.6:
            return 1.0
        elif positive_ratio < 0.4:
            return -1.0
        else:
            return (positive_ratio - 0.5) * 10
    
    @staticmethod
    def calculate_acceleration_score(close_prices: List[float]) -> float:
        """
        加速度因子 - 基于价格变化加速度
        逻辑：价格减速下跌可能是底部信号
        """
        if len(close_prices) < 30:
            return 0
        
        # 计算10日和20日收益率
        ret_10 = (close_prices[-1] - close_prices[-10]) / close_prices[-10]
        ret_20 = (close_prices[-1] - close_prices[-20]) / close_prices[-20]
        
        # 计算加速度（近期速度 - 远期速度）
        acceleration = ret_10 - (ret_20 / 2)
        
        # 使用tanh映射
        return np.tanh(acceleration * 5)


def calculate_ic(factor_values: List[float], forward_returns: List[float]) -> float:
    """计算IC值（Pearson相关系数）"""
    if len(factor_values) < 2 or len(forward_returns) < 2:
        return 0
    
    n = len(factor_values)
    
    # 计算均值
    mean_f = sum(factor_values) / n
    mean_r = sum(forward_returns) / n
    
    # 计算协方差和标准差
    cov = sum((f - mean_f) * (r - mean_r) for f, r in zip(factor_values, forward_returns))
    var_f = sum((f - mean_f) ** 2 for f in factor_values)
    var_r = sum((r - mean_r) ** 2 for r in forward_returns)
    
    if var_f == 0 or var_r == 0:
        return 0
    
    corr = cov / (math.sqrt(var_f) * math.sqrt(var_r))
    
    return corr if not math.isnan(corr) else 0


def analyze_new_factors(db_manager: DatabaseManager, 
                       start_date: str = "2022-01-01",
                       end_date: str = "2024-01-01",
                       max_stocks: int = 100) -> Dict:
    """分析新因子的有效性"""
    
    print("\n" + "="*60)
    print("新因子有效性分析")
    print("="*60)
    
    # 获取股票数据
    print("\n获取股票数据...")
    all_stocks = db_manager.get_all_stocks(limit=max_stocks)
    
    stock_data_dict = {}
    for i, vt_symbol in enumerate(all_stocks):
        if i % 20 == 0:
            print(f"  进度: {i}/{len(all_stocks)}")
        
        data = db_manager.get_stock_data(vt_symbol, start_date, end_date)
        if data and len(data['close']) >= 60:
            stock_data_dict[vt_symbol] = data
    
    print(f"✓ 成功加载 {len(stock_data_dict)} 只股票的数据")
    
    if len(stock_data_dict) < 20:
        print("✗ 数据不足")
        return {}
    
    # 收集因子值和收益
    factor_data = {
        'value': [],
        'quality': [],
        'liquidity': [],
        'consistency': [],
        'acceleration': [],
        'forward_returns': []
    }
    
    print("\n计算因子值...")
    
    # 对每个交易日
    first_stock = list(stock_data_dict.values())[0]
    trading_days = len(first_stock['dates'])
    
    for day in range(60, trading_days - 5):  # 预留5天计算远期收益
        daily_factors = defaultdict(list)
        daily_returns = []
        
        for vt_symbol, data in stock_data_dict.items():
            if day >= len(data['close']):
                continue
            
            hist_close = data['close'][:day]
            hist_volume = data['volume'][:day]
            
            if len(hist_close) < 60:
                continue
            
            try:
                # 计算各因子值
                value = NewFactors.calculate_value_score(hist_close, hist_volume)
                quality = NewFactors.calculate_quality_score(hist_close)
                liquidity = NewFactors.calculate_liquidity_score(hist_volume, hist_close)
                consistency = NewFactors.calculate_consistency_score(hist_close)
                acceleration = NewFactors.calculate_acceleration_score(hist_close)
                
                # 计算5日远期收益
                if day + 5 < len(data['close']):
                    future_return = (data['close'][day + 5] - data['close'][day]) / data['close'][day]
                else:
                    continue
                
                daily_factors['value'].append(value)
                daily_factors['quality'].append(quality)
                daily_factors['liquidity'].append(liquidity)
                daily_factors['consistency'].append(consistency)
                daily_factors['acceleration'].append(acceleration)
                daily_returns.append(future_return)
            except:
                continue
        
        # 添加到总数据
        if len(daily_returns) > 10:
            factor_data['value'].extend(daily_factors['value'])
            factor_data['quality'].extend(daily_factors['quality'])
            factor_data['liquidity'].extend(daily_factors['liquidity'])
            factor_data['consistency'].extend(daily_factors['consistency'])
            factor_data['acceleration'].extend(daily_factors['acceleration'])
            factor_data['forward_returns'].extend(daily_returns)
    
    # 计算IC值
    print("\n计算IC值...")
    
    results = {}
    for factor_name in ['value', 'quality', 'liquidity', 'consistency', 'acceleration']:
        ic = calculate_ic(factor_data[factor_name], factor_data['forward_returns'])
        results[factor_name] = {
            'ic': ic,
            'abs_ic': abs(ic)
        }
    
    return results


def print_results(results: Dict):
    """打印分析结果"""
    print("\n" + "="*60)
    print("新因子IC分析结果")
    print("="*60)
    
    # 按IC绝对值排序
    sorted_factors = sorted(results.items(), key=lambda x: x[1]['abs_ic'], reverse=True)
    
    print(f"\n{'因子名称':<15} {'IC值':>12} {'|IC|':>12} {'评价':<10}")
    print("-"*60)
    
    for factor_name, data in sorted_factors:
        ic = data['ic']
        abs_ic = data['abs_ic']
        
        if ic > 0.03:
            eval_text = "✓ 有效"
        elif ic > 0:
            eval_text = "△ 弱有效"
        elif ic > -0.03:
            eval_text = "✗ 弱无效"
        else:
            eval_text = "✗ 反向"
        
        print(f"{factor_name:<15} {ic:>12.4f} {abs_ic:>12.4f} {eval_text:<10}")
    
    print("="*60)
    
    # 推荐因子
    print("\n推荐使用的因子（IC > 0.03）：")
    recommended = [name for name, data in sorted_factors if data['ic'] > 0.03]
    if recommended:
        for factor in recommended:
            print(f"  ✓ {factor}: IC = {results[factor]['ic']:.4f}")
    else:
        print("  无")
    
    print("\n可尝试的因子（0 < IC < 0.03）：")
    weak = [name for name, data in sorted_factors if 0 < data['ic'] <= 0.03]
    if weak:
        for factor in weak:
            print(f"  △ {factor}: IC = {results[factor]['ic']:.4f}")
    else:
        print("  无")


def main():
    """主函数"""
    print("="*60)
    print("A股新因子挖掘与验证")
    print("="*60)
    print("\n测试因子：")
    print("1. 价值因子 (Value) - 价格/成交量比")
    print("2. 质量因子 (Quality) - 收益分布偏度")
    print("3. 流动性因子 (Liquidity) - Amihud指标")
    print("4. 一致性因子 (Consistency) - 正收益天数占比")
    print("5. 加速度因子 (Acceleration) - 价格变化加速度")
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    results = analyze_new_factors(db_manager)
    
    if results:
        print_results(results)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"new_factor_analysis_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n结果已保存到: {result_file}")
    else:
        print("\n分析失败")


if __name__ == "__main__":
    main()
