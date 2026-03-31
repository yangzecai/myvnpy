#!/usr/bin/env python
"""
因子有效性分析工具
用于验证每个因子的独立有效性和计算IC值
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_db_config():
    """加载数据库配置"""
    # 尝试多个路径
    possible_paths = [
        os.path.join(os.path.dirname(__file__), '.vntrader', 'vt_setting.json'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.vntrader', 'vt_setting.json'),
    ]
    
    config_path = None
    for path in possible_paths:
        if os.path.exists(path):
            config_path = path
            break
    
    if config_path:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return {
            'host': config.get('database.host', 'localhost'),
            'port': config.get('database.port', 3306),
            'user': config.get('database.user', 'root'),
            'password': config.get('database.password', ''),
            'database': config.get('database.database', 'stock'),
        }
    return None


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_config: Dict):
        self.db_config = db_config
        self.db = None
        self._init_database()
    
    def _init_database(self):
        """初始化数据库连接"""
        try:
            from vnpy.trader.setting import SETTINGS
            SETTINGS["database.database"] = self.db_config['database']
            SETTINGS["database.user"] = self.db_config['user']
            SETTINGS["database.password"] = self.db_config['password']
            SETTINGS["database.host"] = self.db_config['host']
            SETTINGS["database.port"] = self.db_config['port']
            
            from vnpy_mysql import Database
            self.db = Database()
            print("✓ 数据库连接成功")
        except Exception as e:
            print(f"✗ 数据库连接失败: {e}")
            self.db = None
    
    def get_all_stocks(self, limit: int = 200) -> List[str]:
        """获取所有股票列表"""
        if not self.db:
            return []
        
        try:
            from vnpy_mysql.mysql_database import DbBarData
            
            query = (DbBarData
                    .select(DbBarData.symbol, DbBarData.exchange)
                    .distinct()
                    .where(DbBarData.interval == 'd'))
            
            stocks = []
            seen = set()
            for row in query:
                vt_symbol = f"{row.symbol}.{row.exchange}"
                if vt_symbol not in seen:
                    stocks.append(vt_symbol)
                    seen.add(vt_symbol)
            
            if limit and len(stocks) > limit:
                stocks = stocks[:limit]
            
            return stocks
        except Exception as e:
            print(f"✗ 获取股票列表失败: {e}")
            return []
    
    def get_stock_data(self, vt_symbol: str, start_date: str, end_date: str) -> Optional[Dict]:
        """获取单只股票数据"""
        if not self.db:
            return None
        
        try:
            parts = vt_symbol.split('.')
            if len(parts) != 2:
                return None
            
            symbol = parts[0]
            exchange_str = parts[1]
            
            from vnpy.trader.object import Interval
            from vnpy.trader.constant import Exchange
            
            exchange_map = {
                'SZSE': Exchange.SZSE,
                'SSE': Exchange.SSE,
            }
            ex = exchange_map.get(exchange_str, Exchange.SSE)
            
            bars = self.db.load_bar_data(
                symbol=symbol,
                exchange=ex,
                interval=Interval.DAILY,
                start=datetime.strptime(start_date, '%Y-%m-%d'),
                end=datetime.strptime(end_date, '%Y-%m-%d')
            )
            
            if not bars or len(bars) < 60:
                return None
            
            return {
                'dates': [bar.datetime for bar in bars],
                'close': [bar.close_price for bar in bars],
                'high': [bar.high_price for bar in bars],
                'low': [bar.low_price for bar in bars],
                'volume': [bar.volume for bar in bars],
                'vt_symbol': vt_symbol,
            }
        except:
            return None


class FactorAnalyzer:
    """因子分析器"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.calculator = OptimizedFactorCalculator()
    
    def calculate_factor_values(self, stock_data: Dict, day: int) -> Dict[str, float]:
        """计算某一天的因子值"""
        if day < 60:
            return {}
        
        hist_close = stock_data['close'][:day]
        hist_high = stock_data['high'][:day]
        hist_low = stock_data['low'][:day]
        hist_volume = stock_data['volume'][:day]
        
        try:
            scores = self.calculator.calculate_composite_score(hist_close, hist_volume)
            return {
                'momentum': scores['momentum'],
                'technical': scores['technical'],
                'volatility': scores['volatility'],
                'volume': scores['volume'],
                'composite': scores['composite'],
            }
        except:
            return {}
    
    def calculate_ic(self, factor_values: List[float], forward_returns: List[float]) -> float:
        """
        计算信息系数 (Information Coefficient)
        IC = corr(factor_value, forward_return)
        """
        if len(factor_values) < 2 or len(factor_values) != len(forward_returns):
            return 0
        
        n = len(factor_values)
        
        # 计算均值
        mean_f = sum(factor_values) / n
        mean_r = sum(forward_returns) / n
        
        # 计算协方差和标准差
        cov = sum((f - mean_f) * (r - mean_r) for f, r in zip(factor_values, forward_returns))
        std_f = math.sqrt(sum((f - mean_f) ** 2 for f in factor_values))
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in forward_returns))
        
        if std_f == 0 or std_r == 0:
            return 0
        
        return cov / (std_f * std_r)
    
    def analyze_factor_ic(self, stock_data_dict: Dict, forward_period: int = 5) -> Dict:
        """
        分析因子IC值
        
        :param stock_data_dict: {vt_symbol: stock_data}
        :param forward_period: 前瞻期（计算未来N天收益）
        :return: IC分析结果
        """
        print(f"\n计算因子IC值（前瞻期: {forward_period}天）...")
        
        # 收集每一天的因子值和未来收益
        daily_data = defaultdict(lambda: {'momentum': [], 'technical': [], 
                                          'volatility': [], 'volume': [],
                                          'composite': [], 'returns': []})
        
        for vt_symbol, data in stock_data_dict.items():
            close_prices = data['close']
            
            for day in range(60, len(close_prices) - forward_period):
                # 计算因子值
                factor_vals = self.calculate_factor_values(data, day)
                if not factor_vals:
                    continue
                
                # 计算未来收益
                current_price = close_prices[day]
                future_price = close_prices[day + forward_period]
                forward_return = (future_price - current_price) / current_price
                
                date_key = data['dates'][day].strftime('%Y-%m-%d')
                
                for factor_name in ['momentum', 'technical', 'volatility', 'volume', 'composite']:
                    daily_data[date_key][factor_name].append(factor_vals[factor_name])
                daily_data[date_key]['returns'].append(forward_return)
        
        # 计算每一天的IC值
        ic_results = {'momentum': [], 'technical': [], 'volatility': [], 'volume': [], 'composite': []}
        
        for date_key, data in daily_data.items():
            if len(data['returns']) < 10:  # 至少需要10只股票
                continue
            
            for factor_name in ic_results.keys():
                ic = self.calculate_ic(data[factor_name], data['returns'])
                ic_results[factor_name].append(ic)
        
        # 计算IC统计指标
        result = {}
        for factor_name, ic_list in ic_results.items():
            if not ic_list:
                continue
            
            n = len(ic_list)
            mean_ic = sum(ic_list) / n
            std_ic = math.sqrt(sum((ic - mean_ic) ** 2 for ic in ic_list) / n) if n > 1 else 0
            ic_ir = mean_ic / std_ic if std_ic > 0 else 0
            
            # 计算IC > 0的比例
            positive_ratio = sum(1 for ic in ic_list if ic > 0) / n
            
            result[factor_name] = {
                'mean_ic': mean_ic,
                'std_ic': std_ic,
                'ic_ir': ic_ir,
                'positive_ratio': positive_ratio,
                'sample_count': n,
            }
        
        return result
    
    def analyze_factor_returns(self, stock_data_dict: Dict) -> Dict:
        """
        分析因子分组收益
        将股票按因子值分为5组，计算每组收益
        """
        print("\n分析因子分组收益...")
        
        quintile_returns = defaultdict(list)
        
        for vt_symbol, data in stock_data_dict.items():
            close_prices = data['close']
            
            for day in range(60, len(close_prices) - 1):
                factor_vals = self.calculate_factor_values(data, day)
                if not factor_vals:
                    continue
                
                # 当日收益
                daily_return = (close_prices[day + 1] - close_prices[day]) / close_prices[day]
                
                # 按因子值分组 (这里简化处理，只记录因子值和收益)
                for factor_name in ['momentum', 'technical', 'volatility', 'volume', 'composite']:
                    quintile_returns[factor_name].append({
                        'factor_value': factor_vals[factor_name],
                        'return': daily_return
                    })
        
        # 计算分组收益
        result = {}
        for factor_name, data_list in quintile_returns.items():
            if len(data_list) < 100:
                continue
            
            # 按因子值排序
            sorted_data = sorted(data_list, key=lambda x: x['factor_value'])
            n = len(sorted_data)
            
            # 分为5组
            group_size = n // 5
            group_returns = []
            
            for i in range(5):
                start_idx = i * group_size
                end_idx = (i + 1) * group_size if i < 4 else n
                group_data = sorted_data[start_idx:end_idx]
                
                avg_return = sum(d['return'] for d in group_data) / len(group_data)
                group_returns.append(avg_return)
            
            # 计算多空收益（最高组 - 最低组）
            long_short_return = group_returns[4] - group_returns[0]
            
            result[factor_name] = {
                'group_returns': group_returns,
                'long_short_return': long_short_return,
                'sample_count': n,
            }
        
        return result
    
    def analyze_factor_correlation(self, stock_data_dict: Dict) -> Dict:
        """分析因子之间的相关性"""
        print("\n分析因子相关性...")
        
        factor_data = {'momentum': [], 'technical': [], 'volatility': [], 'volume': [], 'composite': []}
        
        for vt_symbol, data in stock_data_dict.items():
            for day in range(60, len(data['close'])):
                factor_vals = self.calculate_factor_values(data, day)
                if not factor_vals:
                    continue
                
                for factor_name in factor_data.keys():
                    factor_data[factor_name].append(factor_vals[factor_name])
        
        # 计算相关系数矩阵
        factor_names = list(factor_data.keys())
        corr_matrix = {}
        
        for i, name1 in enumerate(factor_names):
            corr_matrix[name1] = {}
            for j, name2 in enumerate(factor_names):
                if i == j:
                    corr_matrix[name1][name2] = 1.0
                elif i < j:
                    corr = self.calculate_ic(factor_data[name1], factor_data[name2])
                    corr_matrix[name1][name2] = corr
                else:
                    corr_matrix[name1][name2] = corr_matrix[name2][name1]
        
        return corr_matrix
    
    def run_full_analysis(self, start_date: str = "2022-01-01", 
                         end_date: str = "2024-01-01",
                         max_stocks: int = 100) -> Dict:
        """运行完整的因子分析"""
        
        print("="*60)
        print("因子有效性分析")
        print("="*60)
        
        # 获取股票数据
        print("\n获取股票数据...")
        all_stocks = self.db_manager.get_all_stocks(limit=max_stocks)
        
        stock_data_dict = {}
        for i, vt_symbol in enumerate(all_stocks):
            if i % 20 == 0:
                print(f"  进度: {i}/{len(all_stocks)}")
            
            data = self.db_manager.get_stock_data(vt_symbol, start_date, end_date)
            if data and len(data['close']) >= 60:
                stock_data_dict[vt_symbol] = data
        
        print(f"✓ 成功加载 {len(stock_data_dict)} 只股票的数据")
        
        if len(stock_data_dict) < 20:
            print("✗ 数据不足，无法进行分析")
            return {}
        
        # 1. IC分析
        ic_results = self.analyze_factor_ic(stock_data_dict, forward_period=5)
        
        # 2. 分组收益分析
        quintile_results = self.analyze_factor_returns(stock_data_dict)
        
        # 3. 相关性分析
        corr_matrix = self.analyze_factor_correlation(stock_data_dict)
        
        return {
            'ic_analysis': ic_results,
            'quintile_analysis': quintile_results,
            'correlation_matrix': corr_matrix,
            'stock_count': len(stock_data_dict),
        }


def print_analysis_results(results: Dict):
    """打印分析结果"""
    print("\n" + "="*60)
    print("因子分析结果报告")
    print("="*60)
    
    # 1. IC分析结果
    print("\n【因子IC分析】")
    print("-"*60)
    print(f"{'因子':<12} {'IC均值':<10} {'IC标准差':<10} {'IC_IR':<10} {'正IC比例':<10}")
    print("-"*60)
    
    ic_data = results.get('ic_analysis', {})
    for factor_name, data in ic_data.items():
        print(f"{factor_name:<12} {data['mean_ic']:<10.4f} {data['std_ic']:<10.4f} "
              f"{data['ic_ir']:<10.4f} {data['positive_ratio']:<10.2%}")
    
    # 2. 分组收益分析
    print("\n【因子分组收益分析】")
    print("-"*60)
    print(f"{'因子':<12} {'Q1(最低)':<10} {'Q2':<10} {'Q3':<10} {'Q4':<10} {'Q5(最高)':<10} {'多空收益':<10}")
    print("-"*60)
    
    quintile_data = results.get('quintile_analysis', {})
    for factor_name, data in quintile_data.items():
        group_rets = data['group_returns']
        print(f"{factor_name:<12} {group_rets[0]*100:<10.4f} {group_rets[1]*100:<10.4f} "
              f"{group_rets[2]*100:<10.4f} {group_rets[3]*100:<10.4f} {group_rets[4]*100:<10.4f} "
              f"{data['long_short_return']*100:<10.4f}")
    
    # 3. 相关性矩阵
    print("\n【因子相关性矩阵】")
    print("-"*60)
    corr_matrix = results.get('correlation_matrix', {})
    factor_names = list(corr_matrix.keys())
    
    header = f"{'因子':<12}"
    for name in factor_names:
        header += f" {name:<10}"
    print(header)
    print("-"*60)
    
    for name1 in factor_names:
        row = f"{name1:<12}"
        for name2 in factor_names:
            corr = corr_matrix[name1][name2]
            row += f" {corr:<10.4f}"
        print(row)
    
    print("="*60)
    
    # 结论
    print("\n【分析结论】")
    print("-"*60)
    
    # 找出最有效的因子
    best_ic_factor = max(ic_data.items(), key=lambda x: abs(x[1]['mean_ic'])) if ic_data else None
    best_ls_factor = max(quintile_data.items(), key=lambda x: abs(x[1]['long_short_return'])) if quintile_data else None
    
    if best_ic_factor:
        print(f"IC表现最佳因子: {best_ic_factor[0]} (IC={best_ic_factor[1]['mean_ic']:.4f})")
    
    if best_ls_factor:
        print(f"多空收益最佳因子: {best_ls_factor[0]} (收益={best_ls_factor[1]['long_short_return']*100:.4f}%)")
    
    # 检查因子有效性
    effective_factors = []
    for factor_name, data in ic_data.items():
        if abs(data['mean_ic']) > 0.02 and data['positive_ratio'] > 0.55:
            effective_factors.append(factor_name)
    
    if effective_factors:
        print(f"\n有效因子（|IC|>0.02且正IC比例>55%）: {', '.join(effective_factors)}")
    else:
        print("\n警告: 未发现明显有效的因子！")
        print("建议: 重新设计因子或调整因子参数")
    
    print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("A股多因子选股策略 - 因子有效性分析")
    print("="*60)
    
    db_config = load_db_config()
    if not db_config:
        print("✗ 无法读取数据库配置")
        return
    
    db_manager = DatabaseManager(db_config)
    if not db_manager.db:
        print("✗ 数据库连接失败")
        return
    
    analyzer = FactorAnalyzer(db_manager)
    
    results = analyzer.run_full_analysis(
        start_date="2022-01-01",
        end_date="2024-01-01",
        max_stocks=100
    )
    
    if results:
        print_analysis_results(results)
        
        # 保存结果
        result_dir = "backtest_results"
        os.makedirs(result_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = os.path.join(result_dir, f"factor_analysis_{timestamp}.json")
        
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n分析结果已保存到: {result_file}")
    else:
        print("\n分析失败")


if __name__ == "__main__":
    main()
