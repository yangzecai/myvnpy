#!/usr/bin/env python
"""
选股策略回测脚本
用于运行A股多因子选股策略的回测和参数优化
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Tuple

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from strategies.stock_picker_strategy import StockPickerStrategy
from strategies.factors.composite import CompositeScorer


def run_single_backtest(
    symbol: str = "000001.SSE",
    start_date: str = "2022-01-01",
    end_date: str = "2024-01-01",
    initial_capital: float = 1000000.0,
    strategy_params: Dict = None
) -> Dict:
    """
    运行单次回测
    
    :param symbol: 回测标的
    :param start_date: 开始日期
    :param end_date: 结束日期
    :param initial_capital: 初始资金
    :param strategy_params: 策略参数
    :return: 回测结果字典
    """
    try:
        from vnpy_ctabacktester import BacktestingEngine
        from vnpy.trader.constant import Interval
        
        # 默认策略参数
        if strategy_params is None:
            strategy_params = {
                "top_n": 20,
                "rebalance_interval": 1,
                "stop_loss_pct": 0.08,
                "atr_multiplier": 2.0,
                "max_position_pct": 0.95,
                "min_score_threshold": 0.0,
                "momentum_weight": 0.25,
                "technical_weight": 0.30,
                "volatility_weight": 0.20,
                "volume_weight": 0.25,
            }
        
        # 创建回测引擎
        engine = BacktestingEngine()
        
        # 设置回测参数
        engine.set_parameters(
            vt_symbol=symbol,
            interval=Interval.DAILY,
            start=datetime.strptime(start_date, "%Y-%m-%d"),
            end=datetime.strptime(end_date, "%Y-%m-%d"),
            rate=0.0003,      # 佣金率万3
            slippage=0.001,   # 滑点0.1%
            size=1,
            pricetick=0.01,
            capital=initial_capital,
        )
        
        # 添加策略
        engine.add_strategy(StockPickerStrategy, strategy_params)
        
        # 加载数据
        print(f"加载数据: {symbol} ({start_date} ~ {end_date})")
        engine.load_data()
        
        # 运行回测
        print("运行回测...")
        engine.run_backtesting()
        
        # 计算结果
        result_df = engine.calculate_result()
        
        if result_df is None or len(result_df) == 0:
            print("回测结果为空")
            return {}
        
        # 计算绩效指标
        result = calculate_performance(result_df, engine, start_date, end_date, initial_capital)
        
        # 打印结果
        print_performance(result)
        
        return result
        
    except Exception as e:
        print(f"回测失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


def calculate_performance(result_df, engine, start_date, end_date, initial_capital) -> Dict:
    """计算绩效指标"""
    import numpy as np
    
    # 基本指标
    total_return = result_df['balance'].iloc[-1] / result_df['balance'].iloc[0] - 1
    days = len(result_df)
    years = days / 252
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
    
    # 日收益率
    daily_returns = result_df['return'].dropna()
    
    # 夏普比率
    risk_free_rate = 0.03
    if daily_returns.std() != 0:
        excess_returns = daily_returns - risk_free_rate / 252
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / daily_returns.std()
    else:
        sharpe_ratio = 0
    
    # 最大回撤
    cumulative = (1 + daily_returns).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = drawdown.min()
    
    # 最大回撤持续天数
    max_dd_duration = 0
    current_dd_duration = 0
    for dd in drawdown:
        if dd < 0:
            current_dd_duration += 1
            max_dd_duration = max(max_dd_duration, current_dd_duration)
        else:
            current_dd_duration = 0
    
    # 波动率
    volatility = daily_returns.std() * np.sqrt(252)
    
    # 交易统计
    trades = engine.get_all_trades()
    total_trades = len(trades)
    
    # 计算胜率和盈亏比
    if total_trades > 0:
        profits = []
        losses = []
        for trade in trades:
            # 简化的盈亏计算
            pnl = trade.price * trade.volume  # 这里需要更准确的计算
            if hasattr(trade, 'pnl') and trade.pnl is not None:
                if trade.pnl > 0:
                    profits.append(trade.pnl)
                else:
                    losses.append(abs(trade.pnl))
        
        win_rate = len(profits) / total_trades if total_trades > 0 else 0
        avg_profit = np.mean(profits) if profits else 0
        avg_loss = np.mean(losses) if losses else 1
        profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 0
    else:
        win_rate = 0
        profit_loss_ratio = 0
    
    return {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "sharpe_ratio": float(sharpe_ratio),
        "max_drawdown": float(max_drawdown),
        "max_drawdown_duration": int(max_dd_duration),
        "volatility": float(volatility),
        "total_trades": int(total_trades),
        "win_rate": float(win_rate),
        "profit_loss_ratio": float(profit_loss_ratio),
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": float(initial_capital),
        "final_capital": float(result_df['balance'].iloc[-1]),
        "trading_days": int(days),
    }


def print_performance(result: Dict):
    """打印绩效报告"""
    print("\n" + "="*50)
    print("回测绩效报告")
    print("="*50)
    print(f"回测区间: {result.get('start_date', 'N/A')} ~ {result.get('end_date', 'N/A')}")
    print(f"交易天数: {result.get('trading_days', 0)}")
    print(f"初始资金: {result.get('initial_capital', 0):,.2f}")
    print(f"最终资金: {result.get('final_capital', 0):,.2f}")
    print("-"*50)
    print("【收益指标】")
    print(f"  总收益率:    {result.get('total_return', 0)*100:>8.2f}%")
    print(f"  年化收益率:  {result.get('annual_return', 0)*100:>8.2f}%")
    print(f"  夏普比率:    {result.get('sharpe_ratio', 0):>8.4f}")
    print("-"*50)
    print("【风险指标】")
    print(f"  最大回撤:    {result.get('max_drawdown', 0)*100:>8.2f}%")
    print(f"  回撤持续:    {result.get('max_drawdown_duration', 0):>8}天")
    print(f"  年化波动率:  {result.get('volatility', 0)*100:>8.2f}%")
    print("-"*50)
    print("【交易指标】")
    print(f"  总交易次数:  {result.get('total_trades', 0):>8}")
    print(f"  胜率:        {result.get('win_rate', 0)*100:>8.2f}%")
    print(f"  盈亏比:      {result.get('profit_loss_ratio', 0):>8.2f}")
    print("="*50)
    
    # 夏普率评估
    sharpe = result.get('sharpe_ratio', 0)
    if sharpe >= 1.0:
        print(f"✓ 夏普率达到目标: {sharpe:.4f} >= 1.0")
    else:
        print(f"✗ 夏普率未达标: {sharpe:.4f} < 1.0")
    print("="*50 + "\n")


def optimize_parameters(
    symbol: str = "000001.SSE",
    start_date: str = "2022-01-01",
    end_date: str = "2023-01-01",
    initial_capital: float = 1000000.0,
) -> List[Tuple[Dict, Dict]]:
    """
    参数优化
    测试不同的参数组合，找出最优参数
    """
    print("开始参数优化...")
    
    # 定义参数网格
    param_grid = {
        "top_n": [10, 15, 20, 25],
        "stop_loss_pct": [0.05, 0.08, 0.10],
        "momentum_weight": [0.20, 0.25, 0.30],
        "technical_weight": [0.25, 0.30, 0.35],
        "volatility_weight": [0.15, 0.20, 0.25],
        "volume_weight": [0.20, 0.25, 0.30],
    }
    
    # 为了节省时间，只测试部分组合
    test_params = [
        {
            "top_n": 20,
            "stop_loss_pct": 0.08,
            "momentum_weight": 0.25,
            "technical_weight": 0.30,
            "volatility_weight": 0.20,
            "volume_weight": 0.25,
        },
        {
            "top_n": 15,
            "stop_loss_pct": 0.08,
            "momentum_weight": 0.30,
            "technical_weight": 0.35,
            "volatility_weight": 0.15,
            "volume_weight": 0.20,
        },
        {
            "top_n": 25,
            "stop_loss_pct": 0.05,
            "momentum_weight": 0.20,
            "technical_weight": 0.25,
            "volatility_weight": 0.25,
            "volume_weight": 0.30,
        },
        {
            "top_n": 20,
            "stop_loss_pct": 0.10,
            "momentum_weight": 0.35,
            "technical_weight": 0.25,
            "volatility_weight": 0.20,
            "volume_weight": 0.20,
        },
    ]
    
    results = []
    
    for i, params in enumerate(test_params):
        print(f"\n测试参数组合 {i+1}/{len(test_params)}: {params}")
        
        result = run_single_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            strategy_params=params
        )
        
        if result:
            results.append((params, result))
    
    # 按夏普比率排序
    results.sort(key=lambda x: x[1].get('sharpe_ratio', 0), reverse=True)
    
    print("\n" + "="*50)
    print("参数优化结果排名")
    print("="*50)
    for i, (params, result) in enumerate(results[:5]):
        print(f"\n第{i+1}名:")
        print(f"  参数: {params}")
        print(f"  夏普率: {result.get('sharpe_ratio', 0):.4f}")
        print(f"  年化收益: {result.get('annual_return', 0)*100:.2f}%")
        print(f"  最大回撤: {result.get('max_drawdown', 0)*100:.2f}%")
    
    return results


def save_result(result: Dict, filename: str = None):
    """保存回测结果到文件"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_result_{timestamp}.json"
    
    # 确保目录存在
    result_dir = "backtest_results"
    os.makedirs(result_dir, exist_ok=True)
    
    filepath = os.path.join(result_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"结果已保存到: {filepath}")


def main():
    """主函数"""
    print("="*50)
    print("A股多因子选股策略回测系统")
    print("="*50)
    
    # 回测参数
    symbol = "000001.SSE"  # 上证指数作为示例
    start_date = "2022-01-01"
    end_date = "2024-01-01"
    initial_capital = 1000000.0
    
    print(f"\n回测设置:")
    print(f"  标的: {symbol}")
    print(f"  区间: {start_date} ~ {end_date}")
    print(f"  初始资金: {initial_capital:,.2f}")
    
    # 询问用户选择
    print("\n请选择操作:")
    print("1. 运行单次回测")
    print("2. 参数优化")
    print("3. 使用最优参数运行完整回测")
    
    choice = input("\n请输入选项 (1/2/3): ").strip()
    
    if choice == "1":
        # 单次回测
        result = run_single_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital
        )
        
        if result:
            save_result(result)
    
    elif choice == "2":
        # 参数优化
        optimize_start = "2022-01-01"
        optimize_end = "2023-01-01"
        
        results = optimize_parameters(
            symbol=symbol,
            start_date=optimize_start,
            end_date=optimize_end,
            initial_capital=initial_capital
        )
        
        # 保存优化结果
        if results:
            best_params, best_result = results[0]
            save_result({
                "best_params": best_params,
                "result": best_result,
                "all_results": [{"params": p, "result": r} for p, r in results]
            }, "optimization_result.json")
    
    elif choice == "3":
        # 使用优化后的参数运行完整回测
        best_params = {
            "top_n": 20,
            "rebalance_interval": 1,
            "stop_loss_pct": 0.08,
            "atr_multiplier": 2.0,
            "max_position_pct": 0.95,
            "min_score_threshold": 0.0,
            "momentum_weight": 0.30,
            "technical_weight": 0.35,
            "volatility_weight": 0.15,
            "volume_weight": 0.20,
        }
        
        print("\n使用优化参数:")
        for k, v in best_params.items():
            print(f"  {k}: {v}")
        
        result = run_single_backtest(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            strategy_params=best_params
        )
        
        if result:
            save_result(result, "final_backtest_result.json")
    
    else:
        print("无效选项")


if __name__ == "__main__":
    main()