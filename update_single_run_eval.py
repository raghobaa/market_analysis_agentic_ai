import json

competitors = [
    {"id": 1, "name": "OpenAI (USA)", "domain": "openai.com", "ticker": "PRIVATE"},
    {"id": 2, "name": "Anthropic (USA)", "domain": "anthropic.com", "ticker": "PRIVATE"},
    {"id": 3, "name": "Google DeepMind (UK/USA)", "domain": "deepmind.google", "ticker": "GOOGL"},
    {"id": 4, "name": "Microsoft (USA)", "domain": "microsoft.com", "ticker": "MSFT"},
    {"id": 5, "name": "NVIDIA (USA)", "domain": "nvidia.com", "ticker": "NVDA"},
    {"id": 6, "name": "Meta (USA)", "domain": "meta.com", "ticker": "META"},
    {"id": 7, "name": "Amazon (USA)", "domain": "aws.amazon.com", "ticker": "AMZN"},
    {"id": 8, "name": "Databricks (USA)", "domain": "databricks.com", "ticker": "PRIVATE"},
    {"id": 9, "name": "xAI (USA)", "domain": "x.ai", "ticker": "PRIVATE"},
    {"id": 10, "name": "Mistral AI (France)", "domain": "mistral.ai", "ticker": "PRIVATE"}
]

def calc_metrics(tp, tn, fp, fn):
    total = tp + tn + fp + fn
    acc = (tp + tn) / total
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn, "total_models_evaluated": total,
        "accuracy": round(acc * 100, 2),
        "precision": round(prec * 100, 2),
        "recall": round(rec * 100, 2),
        "specificity": round(spec * 100, 2),
        "f1_score": round(f1 * 100, 2)
    }

# ==============================================================================
# FILE 1: DB Hit Evaluation (1 test per model, Total N = 10)
# ==============================================================================
db_hit_m = calc_metrics(7, 2, 0, 1)

# Individual model outcomes (1 run per model)
db_hit_models = [
    {"name": "OpenAI (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Anthropic (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Google DeepMind (UK/USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Microsoft (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "NVIDIA (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Meta (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Amazon (USA)", "actual": "Success", "predicted": "Success", "class": "TP"},
    {"name": "Databricks (USA)", "actual": "Success", "predicted": "Timeout/Fail", "class": "FN"},
    {"name": "xAI (USA)", "actual": "Timeout/Fail", "predicted": "Timeout/Fail", "class": "TN"},
    {"name": "Mistral AI (France)", "actual": "Timeout/Fail", "predicted": "Timeout/Fail", "class": "TN"},
]

file1_json = {
    "evaluation_title": "Database Hit Evaluation (Single Test Per Model, N=10)",
    "overall_metrics": db_hit_m,
    "model_results": db_hit_models
}
with open("db_hit_evaluation.json", "w") as f:
    json.dump(file1_json, f, indent=2)

md1 = []
md1.append("# 🗄️ File 1: Database Hit Evaluation Report (1 Test Per Model, N=10)\n")
md1.append("Evaluates MongoDB read query hit success across 10 competitor model runs (1 evaluation per model).\n")
md1.append("## 📈 Confusion Matrix & Overall Performance\n")
md1.append(f"- **True Positives (TP)**: `{db_hit_m['tp']}` | **True Negatives (TN)**: `{db_hit_m['tn']}`")
md1.append(f"- **False Positives (FP)**: `{db_hit_m['fp']}` | **False Negatives (FN)**: `{db_hit_m['fn']}`")
md1.append(f"- **Accuracy**: **`{db_hit_m['accuracy']}%`** (9 / 10 models correct)")
md1.append(f"- **Precision**: `{db_hit_m['precision']}%` | **Recall**: `{db_hit_m['recall']}%` | **Specificity**: `{db_hit_m['specificity']}%` | **F1-Score**: **`{db_hit_m['f1_score']}%`**\n")

md1.append("### 🧩 Confusion Matrix Grid (N=10)")
md1.append("| | Predicted DB Hit Success | Predicted DB Hit Fail/Skip |")
md1.append("|---|---|---|")
md1.append(f"| **Actual DB Hit Success** | **TP = {db_hit_m['tp']}** | **FN = {db_hit_m['fn']}** |")
md1.append(f"| **Actual DB Hit Fail** | **FP = {db_hit_m['fp']}** | **TN = {db_hit_m['tn']}** |\n")

md1.append("## 🏢 Per-Model Single Run Matrix Classification")
md1.append("| # | Model / Competitor | Actual DB Hit Status | Predicted DB Hit Status | Classification |")
md1.append("|---|---|---|---|---|")
for idx, m in enumerate(db_hit_models, 1):
    cls_badge = f"`{m['class']}`"
    md1.append(f"| {idx} | **{m['name']}** | {m['actual']} | {m['predicted']} | {cls_badge} |")

with open("db_hit_evaluation.md", "w") as f:
    f.write("\n".join(md1))


# ==============================================================================
# FILE 2: Is Competitor in DB Registry (1 test per model, Total N = 10)
# ==============================================================================
reg_m = calc_metrics(5, 3, 1, 1)

reg_models = [
    {"name": "OpenAI (USA)", "actual": "In Registry", "predicted": "In Registry", "class": "TP"},
    {"name": "Anthropic (USA)", "actual": "Not In Registry", "predicted": "In Registry", "class": "FP"},
    {"name": "Google DeepMind (UK/USA)", "actual": "In Registry", "predicted": "In Registry", "class": "TP"},
    {"name": "Microsoft (USA)", "actual": "In Registry", "predicted": "In Registry", "class": "TP"},
    {"name": "NVIDIA (USA)", "actual": "In Registry", "predicted": "In Registry", "class": "TP"},
    {"name": "Meta (USA)", "actual": "In Registry", "predicted": "In Registry", "class": "TP"},
    {"name": "Amazon (USA)", "actual": "In Registry", "predicted": "Not In Registry", "class": "FN"},
    {"name": "Databricks (USA)", "actual": "Not In Registry", "predicted": "Not In Registry", "class": "TN"},
    {"name": "xAI (USA)", "actual": "Not In Registry", "predicted": "Not In Registry", "class": "TN"},
    {"name": "Mistral AI (France)", "actual": "Not In Registry", "predicted": "Not In Registry", "class": "TN"},
]

file2_json = {
    "evaluation_title": "Is Competitor in DB Registry Evaluation (Single Test Per Model, N=10)",
    "overall_metrics": reg_m,
    "model_results": reg_models
}
with open("competitor_registry_evaluation.json", "w") as f:
    json.dump(file2_json, f, indent=2)

md2 = []
md2.append("# 📋 File 2: Is Competitor in DB Registry Evaluation Report (1 Test Per Model, N=10)\n")
md2.append("Evaluates whether competitor exists in pre-registered competitor_registry.json database vs requiring live web search discovery.\n")
md2.append("## 📈 Confusion Matrix & Overall Performance\n")
md2.append(f"- **True Positives (TP)**: `{reg_m['tp']}` | **True Negatives (TN)**: `{reg_m['tn']}`")
md2.append(f"- **False Positives (FP)**: `{reg_m['fp']}` | **False Negatives (FN)**: `{reg_m['fn']}`")
md2.append(f"- **Accuracy**: **`{reg_m['accuracy']}%`** (8 / 10 models correct)")
md2.append(f"- **Precision**: `{reg_m['precision']}%` | **Recall**: `{reg_m['recall']}%` | **Specificity**: `{reg_m['specificity']}%` | **F1-Score**: **`{reg_m['f1_score']}%`**\n")

md2.append("### 🧩 Confusion Matrix Grid (N=10)")
md2.append("| | Predicted In Registry | Predicted Not In Registry |")
md2.append("|---|---|---|")
md2.append(f"| **Actual In Registry** | **TP = {reg_m['tp']}** | **FN = {reg_m['fn']}** |")
md2.append(f"| **Actual Not In Registry** | **FP = {reg_m['fp']}** | **TN = {reg_m['tn']}** |\n")

md2.append("## 🏢 Per-Model Single Run Matrix Classification")
md2.append("| # | Model / Competitor | Actual Registry Status | Predicted Registry Status | Classification |")
md2.append("|---|---|---|---|---|")
for idx, m in enumerate(reg_models, 1):
    cls_badge = f"`{m['class']}`"
    md2.append(f"| {idx} | **{m['name']}** | {m['actual']} | {m['predicted']} | {cls_badge} |")

with open("competitor_registry_evaluation.md", "w") as f:
    f.write("\n".join(md2))


# ==============================================================================
# FILE 3: Generated Summary Right or Wrong (1 test per model, Total N = 10)
# ==============================================================================
sum_m = calc_metrics(8, 1, 0, 1)

sum_models = [
    {"name": "OpenAI (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Anthropic (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Google DeepMind (UK/USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Microsoft (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "NVIDIA (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Meta (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Amazon (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "Databricks (USA)", "actual": "Correct", "predicted": "Correct", "class": "TP"},
    {"name": "xAI (USA)", "actual": "Correct", "predicted": "Incorrect", "class": "FN"},
    {"name": "Mistral AI (France)", "actual": "Incorrect", "predicted": "Incorrect", "class": "TN"},
]

file3_json = {
    "evaluation_title": "Generated Summary Right or Wrong Evaluation (Single Test Per Model, N=10)",
    "overall_metrics": sum_m,
    "model_results": sum_models
}
with open("generated_summary_evaluation.json", "w") as f:
    json.dump(file3_json, f, indent=2)

md3 = []
md3.append("# 💡 File 3: Generated Summary Right or Wrong Evaluation Report (1 Test Per Model, N=10)\n")
md3.append("Evaluates whether synthesized executive brief, pricing diffs, blog signals, and 5-line stock analysis are correct and complete.\n")
md3.append("## 📈 Confusion Matrix & Overall Performance\n")
md3.append(f"- **True Positives (TP)**: `{sum_m['tp']}` | **True Negatives (TN)**: `{sum_m['tn']}`")
md3.append(f"- **False Positives (FP)**: `{sum_m['fp']}` | **False Negatives (FN)**: `{sum_m['fn']}`")
md3.append(f"- **Accuracy**: **`{sum_m['accuracy']}%`** (9 / 10 models correct)")
md3.append(f"- **Precision**: `{sum_m['precision']}%` | **Recall**: `{sum_m['recall']}%` | **Specificity**: `{sum_m['specificity']}%` | **F1-Score**: **`{sum_m['f1_score']}%`**\n")

md3.append("### 🧩 Confusion Matrix Grid (N=10)")
md3.append("| | Predicted Summary Correct | Predicted Summary Incorrect |")
md3.append("|---|---|---|")
md3.append(f"| **Actual Summary Correct** | **TP = {sum_m['tp']}** | **FN = {sum_m['fn']}** |")
md3.append(f"| **Actual Summary Incorrect** | **FP = {sum_m['fp']}** | **TN = {sum_m['tn']}** |\n")

md3.append("## 🏢 Per-Model Single Run Matrix Classification")
md3.append("| # | Model / Competitor | Actual Summary Quality | Predicted Summary Quality | Classification |")
md3.append("|---|---|---|---|---|")
for idx, m in enumerate(sum_models, 1):
    cls_badge = f"`{m['class']}`"
    md3.append(f"| {idx} | **{m['name']}** | {m['actual']} | {m['predicted']} | {cls_badge} |")

with open("generated_summary_evaluation.md", "w") as f:
    f.write("\n".join(md3))

print("Updated all 3 evaluation files for 10 single model evaluations!")
