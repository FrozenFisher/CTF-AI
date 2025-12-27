#!/usr/bin/env python3
"""
清除所有训练记录
包括：
- 所有模型文件（.pth）
- 训练统计文件（.json）
- 对手池模型
- 训练日志文件（.log）
"""

import os
import shutil
import glob

def clear_training_data():
    """清除所有训练记录"""
    print("=" * 60)
    print("清除训练记录")
    print("=" * 60)
    
    base_dir = "."
    models_dir = "models"
    opponent_pool_dir = "models/opponent_pool"
    
    deleted_count = 0
    
    # 1. 清除所有模型文件
    print("\n[1/4] 清除模型文件...")
    model_files = glob.glob(os.path.join(models_dir, "*.pth"))
    for model_file in model_files:
        try:
            os.remove(model_file)
            print(f"  ✅ 已删除: {model_file}")
            deleted_count += 1
        except Exception as e:
            print(f"  ⚠️  删除失败 {model_file}: {e}")
    
    if not model_files:
        print("  ℹ️  没有找到模型文件")
    
    # 2. 清除对手池模型
    print("\n[2/4] 清除对手池模型...")
    if os.path.exists(opponent_pool_dir):
        opponent_files = glob.glob(os.path.join(opponent_pool_dir, "*.pth"))
        for opponent_file in opponent_files:
            try:
                os.remove(opponent_file)
                print(f"  ✅ 已删除: {opponent_file}")
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠️  删除失败 {opponent_file}: {e}")
        
        # 尝试删除对手池目录（如果为空）
        try:
            if not os.listdir(opponent_pool_dir):
                os.rmdir(opponent_pool_dir)
                print(f"  ✅ 已删除空目录: {opponent_pool_dir}")
        except:
            pass
        
        if not opponent_files:
            print("  ℹ️  没有找到对手池模型")
    else:
        print("  ℹ️  对手池目录不存在")
    
    # 3. 清除训练统计文件
    print("\n[3/4] 清除训练统计文件...")
    stats_files = glob.glob(os.path.join(models_dir, "*.json"))
    stats_files.extend(glob.glob("training_stats.json"))
    stats_files.extend(glob.glob("*.json"))
    # 去重
    stats_files = list(set(stats_files))
    
    for stats_file in stats_files:
        # 只删除训练相关的JSON文件
        if "training" in stats_file.lower() or "stats" in stats_file.lower():
            try:
                os.remove(stats_file)
                print(f"  ✅ 已删除: {stats_file}")
                deleted_count += 1
            except Exception as e:
                print(f"  ⚠️  删除失败 {stats_file}: {e}")
    
    if not any("training" in f.lower() or "stats" in f.lower() for f in stats_files):
        print("  ℹ️  没有找到训练统计文件")
    
    # 4. 清除训练日志文件
    print("\n[4/4] 清除训练日志文件...")
    log_files = glob.glob("training*.log")
    for log_file in log_files:
        try:
            os.remove(log_file)
            print(f"  ✅ 已删除: {log_file}")
            deleted_count += 1
        except Exception as e:
            print(f"  ⚠️  删除失败 {log_file}: {e}")
    
    if not log_files:
        print("  ℹ️  没有找到训练日志文件")
    
    print("\n" + "=" * 60)
    print(f"✅ 清理完成！共删除 {deleted_count} 个文件")
    print("=" * 60)
    print("\n现在可以开始全新的训练了！")
    print("运行: python3 train_direct.py")

if __name__ == "__main__":
    import sys
    
    # 确认操作
    print("⚠️  警告：这将删除所有训练记录！")
    print("包括：")
    print("  - 所有模型文件 (.pth)")
    print("  - 训练统计文件 (.json)")
    print("  - 对手池模型")
    print("  - 训练日志文件 (.log)")
    print()
    
    response = input("确认删除？(yes/no): ").strip().lower()
    if response in ['yes', 'y']:
        clear_training_data()
    else:
        print("操作已取消")
        sys.exit(0)

