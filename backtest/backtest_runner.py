"""
回测运行器
用于运行策略回测并分析结果
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class BacktestResult:
    """回测结果数据类"""
    # 收益指标
    total_return: float = 0.0           # 总收益率
    annual_return: float = 0.0          # 年化收益率
    sharpe_ratio: float = 0.0           # 夏普比率
    
    # 风险指标
    max_drawdown: float = 0.0           # 最大回撤
    max_drawdown_duration: int = 0      # 最大回撤持续天数
    volatility: float = 0.0             # 波动率
    
    # 交易指标
    total_trades: int = 0               # 总交易次数
    win_rate: float = 0.0               # 胜率
    profit_loss_ratio: float = 0.0      # 盈亏比
    
    # 其他
    start_date: str = ""                # 回测开始日期
    end_date: str = ""                  # 回测结束日期
    initial_capital: float = 0.0        # 初始资金
    final_capital: float = 0.0          # 最终资金
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"""
========================================
回测结果报告
========================================
回测区间: {self.start_date} ~ {self.end_date}
初始资金: {self.initial_capital:,.2f}
最终资金: {self.final_capital:,.2f}

【收益指标】
总收益率: {self.total_return*100:.2f}%
年化收益率: {self.annual_return*100:.2f}%
夏普比率: {self.sharpe_ratio:.4f}

【风险指标】
最大回撤: {self.max_drawdown*100:.2f}%
最大回撤持续: {self.max_drawdown_duration}天
年化波动率: {self.volatility*100:.2f}%

【交易指标】
总交易次数: {self.total_trades}
胜率: {self.win_rate*100:.2f}%
盈亏比: {self.profit_loss_ratio:.2f}
========================================
"""


class BacktestRunner:
    """
    回测运行器
    
    用于运行选股策略回测并计算绩效指标
    """
    
    def __init__(self, 
                 strategy_class,
                 start_date: str,
                 end_date: str,
                 initial_capital: float = 1000000.0,
                 commission_rate: float = 0.0003,  # 佣金率 (万3)
                 slippage: float = 0.001,          # 滑点 (0.1%)
                 ):
        """
        初始化回测运行器
        
        :param strategy_class: 策略类
        :param start_date: 回测开始日期 (YYYY-MM-DD)
        :param end_date: 回测结束日期 (YYYY-MM-DD)
        :param initial_capital: 初始资金
        :param commission_rate: 佣金率
        :param slippage: 滑点
        """
        self.strategy_class = strategy_class
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        
        # 回测数据
        self.daily_returns: List[float] = []
        self.daily_capital: List[float] = []
        self.trade_records: List[Dict] = []
        
    def run_backtest(self, 
                    vt_symbols: List[str],
                    strategy_params: Optional[Dict] = None) -> BacktestResult:
        """
        运行回测
        
        :param vt_symbols: 回测标的列表
        :param strategy_params: 策略参数字典
        :return: 回测结果
        """
        from vnpy_ctabacktester import BacktestingEngine
        from vnpy.trader.constant import Interval
        
        # 创建回测引擎
        engine = BacktestingEngine()
        
        # 设置回测参数
        engine.set_parameters(
            vt_symbol=vt_symbols[0],  # 主标的
            interval=Interval.DAILY,
            start=datetime.strptime(self.start_date, "%Y-%m-%d"),
            end=datetime.strptime(self.end_date, "%Y-%m-%d"),
            rate=self.commission_rate,
            slippage=self.slippage,
            size=1,
            pricetick=0.01,
            capital=self.initial_capital,
        )
        
        # 添加策略
        if strategy_params is None:
            strategy_params = {}
        
        engine.add_strategy(self.strategy_class, strategy_params)
        
        # 加载数据并运行回测
        engine.load_data()
        engine.run_backtesting()
        
        # 计算结果
        result = engine.calculate_result()
        
        # 生成回测报告
        backtest_result = self._analyze_result(result, engine)
        
        return backtest_result
    
    def _analyze_result(self, 
                       result_df,
                       engine) -> BacktestResult:
        """
        分析回测结果
        """
        if result_df is None or len(result_df) == 0:
            return BacktestResult()
        
        # 计算收益指标
        total_return = result_df['balance'].iloc[-1] / result_df['balance'].iloc[0] - 1
        
        # 计算年化收益
        days = len(result_df)
        years = days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 计算日收益率
        daily_returns = result_df['return'].dropna()
        
        # 计算夏普比率
        risk_free_rate = 0.03  # 假设无风险利率3%
        excess_returns = daily_returns - risk_free_rate / 252
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0
        
        # 计算最大回撤
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # 计算最大回撤持续天数
        max_dd_duration = 0
        current_dd_duration = 0
        for dd in drawdown:
            if dd < 0:
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)
            else:
                current_dd_duration = 0
        
        # 计算波动率
        volatility = daily_returns.std() * np.sqrt(252)
        
        # 获取交易统计
        trades = engine.get_all_trades()
        total_trades = len(trades)
        
        # 计算胜率和盈亏比
        if total_trades > 0:
            # 简化计算，实际需要更复杂的逻辑
            win_rate = 0.5  # 占位
            profit_loss_ratio = 1.0  # 占位
        else:
            win_rate = 0.0
            profit_loss_ratio = 0.0
        
        return BacktestResult(
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            volatility=volatility,
            total_trades=total_trades,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            start_date=self.start_date,
            end_date=self.end_date,
            initial_capital=self.initial_capital,
            final_capital=result_df['balance'].iloc[-1],
        )
    
    def optimize_parameters(self,
                          vt_symbols: List[str],
                          param_grid: Dict[str, List]) -> List[Tuple[Dict, BacktestResult]]:
        """
        参数优化
        
        :param vt_symbols: 回测标的列表
        :param param_grid: 参数网格 {param_name: [values]}
        :return: [(params, result), ...] 按夏普比率排序
        """
        from itertools import product
        
        results = []
        
        # 生成参数组合
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        
        for values in product(*param_values):
            params = dict(zip(param_names, values))
            
            try:
                result = self.run_backtest(vt_symbols, params)
                results.append((params, result))
                print(f"参数: {params}, 夏普率: {result.sharpe_ratio:.4f}")
            except Exception as e:
                print(f"参数回测失败 {params}: {e}")
                continue
        
        # 按夏普比率排序
        results.sort(key=lambda x: x[1].sharpe_ratio, reverse=True)
        
        return results
    
    def save_result(self, result: BacktestResult, filepath: str):
        """
        保存回测结果到文件
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"回测结果已保存到: {filepath}")


def run_stock_picker_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-01-01",
    initial_capital: float = 1000000.0,
    vt_symbols: Optional[List[str]] = None
) -> BacktestResult:
    """
    运行选股策略回测的便捷函数
    
    :param start_date: 回测开始日期
    :param end_date: 回测结束日期
    :param initial_capital: 初始资金
    :param vt_symbols: 回测标的列表，默认为None（使用示例标的）
    :return: 回测结果
    """
    from strategies.stock_picker_strategy import StockPickerStrategy
    
    if vt_symbols is None:
        # 示例标的（实际应该使用全市场股票）
        vt_symbols = [
            "000001.SSE",  # 上证指数
            "000002.SSE",  # 示例
        ]
    
    runner = BacktestRunner(
        strategy_class=StockPickerStrategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
    )
    
    # 策略参数
    strategy_params = {
        "top_n": 20,
        "stop_loss_pct": 0.08,
        "momentum_weight": 0.25,
        "technical_weight": 0.30,
        "volatility_weight": 0.20,
        "volume_weight": 0.25,
    }
    
    result = runner.run_backtest(vt_symbols, strategy_params)
    
    print(result)
    
    # 保存结果
    result_dir = "backtest_results"
    os.makedirs(result_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = f"{result_dir}/backtest_{timestamp}.json"
    runner.save_result(result, result_file)
    
    return result


if __name__ == "__main__":
    # 运行回测示例
    result = run_stock_picker_backtest()
    print(f"\n夏普比率: {result.sharpe_ratio:.4f}")