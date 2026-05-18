import matplotlib.pyplot as plt
import numpy as np


def compare_policies(results, output_dir="output"):
    """Generate comparison charts for all policies."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    names = list(results.keys())
    if not names:
        return

    # Color palette
    colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"][:len(names)]

    # 1. Average order prep time
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Warehouse Simulation: Policy Comparison", fontsize=14, fontweight="bold")

    # Prep time
    ax = axes[0, 0]
    vals = [results[n]["avg_prep_time"] for n in names]
    ax.bar(names, vals, color=colors)
    ax.set_ylabel("Minutes")
    ax.set_title("Avg Order Preparation Time")
    ax.tick_params(axis="x", rotation=15)

    # Wait time
    ax = axes[0, 1]
    vals = [results[n]["avg_wait_time"] for n in names]
    ax.bar(names, vals, color=colors)
    ax.set_ylabel("Minutes")
    ax.set_title("Avg Reach Truck Wait Time")
    ax.tick_params(axis="x", rotation=15)

    # Walk distance
    ax = axes[1, 0]
    vals = [results[n]["avg_walk_distance"] for n in names]
    ax.bar(names, vals, color=colors)
    ax.set_ylabel("Meters")
    ax.set_title("Avg Walk Distance per Order")
    ax.tick_params(axis="x", rotation=15)

    # Resource utilization
    ax = axes[1, 1]
    x = np.arange(len(names))
    w = 0.35
    rt_vals = [results[n]["reach_truck_utilization"] * 100 for n in names]
    op_vals = [results[n]["operator_utilization"] * 100 for n in names]
    ax.bar(x - w / 2, rt_vals, w, label="Reach Truck", color="#e74c3c")
    ax.bar(x + w / 2, op_vals, w, label="Operator", color="#3498db")
    ax.set_ylabel("Utilization %")
    ax.set_title("Resource Utilization")
    ax.set_xticks(x)
    ax.set_xticklabels(names, rotation=15)
    ax.legend()

    plt.tight_layout()
    plt.savefig(f"{output_dir}/policy_comparison.png", dpi=150)
    plt.close()

    # 2. Summary table as text
    print("\n" + "=" * 108)
    print(f"{'Policy':<28} {'Orders':>7} {'Prep':>7} {'Lead':>7} "
          f"{'OpQ':>6} {'RTQ':>6} {'Dist':>7} {'RT%':>6} {'Op%':>6}")
    print("-" * 108)
    for n in names:
        r = results[n]
        print(f"{n:<28} {r.get('orders_completed', 0):>7.0f} "
              f"{r.get('avg_prep_time', 0):>6.2f}m {r.get('avg_lead_time', 0):>6.2f}m "
              f"{r.get('avg_op_queue_wait', 0):>5.2f}m {r.get('avg_wait_time', 0):>5.2f}m "
              f"{r.get('avg_walk_distance', 0):>6.1f}m "
              f"{r.get('reach_truck_utilization', 0) * 100:>5.1f}% "
              f"{r.get('operator_utilization', 0) * 100:>5.1f}%")
    print("=" * 108)


def plot_prep_time_distribution(all_kpis, output_dir="output"):
    """Box plot of prep time distributions across policies."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    data = []
    labels = []
    for name, kpi in all_kpis.items():
        prep_times = [o.prep_time for o in kpi.orders]
        data.append(prep_times)
        labels.append(name)

    ax.boxplot(data, labels=labels, showfliers=False)
    ax.set_ylabel("Order Preparation Time (minutes)")
    ax.set_title("Prep Time Distribution by Policy")
    ax.tick_params(axis="x", rotation=15)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/prep_time_boxplot.png", dpi=150)
    plt.close()
