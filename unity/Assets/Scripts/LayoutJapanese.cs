using System;
using System.Text;
using System.Text.RegularExpressions;

namespace FurnitureLayout
{
    // Translate presentation only; API keys, enum values and scores remain unchanged.
    public static class LayoutJapanese
    {
        public static string Name(string key) => key switch
        {
            "shelf" or "Shelf" => "棚", "bed" or "Bed" => "ベッド",
            "table" or "Table" => "テーブル", "tv_unit" or "TV stand" or "TV Unit" => "テレビ台",
            "chair" or "Chair" => "椅子", "ceiling_light" or "Ceiling Light" or "Ceiling light" => "天井照明",
            "door" or "door_1" or "Door" => "ドア", "window" or "window_1" or "Window" => "窓",
            _ => key ?? "対象不明"
        };
        public static string Restraint(string value) => value switch
        {
            "none" => "なし", "wall_bracket" => "壁への金具固定", "belt" => "ベルト等",
            "pole" => "突っ張り棒", "pole_combination" => "突っ張り棒と補助器具の併用",
            "other" => "その他", _ => "不明"
        };
        public static string Protection(string value) => value=="present" ? "あり" : value=="none" ? "なし" : "不明";
        public static string Installation(bool confirmed) => confirmed ? "利用者が確認済み" : "未確認・要再確認";
        public static string Direction(string value) => value switch
        {
            "NORTH" => "前方への転倒", "SOUTH" => "後方への転倒", "EAST" => "右側への転倒",
            "WEST" => "左側への転倒", "DOWN" or "drop" => "真下への落下", _ => "方向未確認"
        };
        public static string JobStatus(string value) => value switch
        {
            "queued" => "探索の開始待ち", "running" => "配置を探索中",
            "succeeded" => "探索完了", "failed" => "探索に失敗しました", _ => "探索状況を確認中"
        };
        public static string ScoreName(string value) => value switch
        {
            "clearance_violation" => "家具の利用空間の不足", "circulation_penalty" => "室内の移動しにくさ",
            "pairwise_distance_penalty" => "家具間の距離", "conversation_penalty" => "会話する席の距離",
            "visual_balance_penalty" => "配置の重心の偏り", "alignment_penalty" => "壁沿いの配置",
            "window_proximity_penalty" => "窓への近さ", "safety_violations" => "安全条件の違反",
            "safety_overlap" => "危険領域の重なり", "primary_overlap" => "主要方向の重なり",
            "invalid_layout" => "配置できない領域への侵入", _ => "追加の評価項目"
        };
        public static string Scenario(string id)
        {
            if (id=="baseline") return "平常時";
            var parts=(id ?? "").Split(':');
            return parts.Length==2 ? Name(parts[0])+"の"+Direction(parts[1]) : "危険シナリオ";
        }
        public static string Issue(SafetyIssue issue)
        {
            if (issue.kind=="escape_blocked")
                return $"{Scenario(issue.scenario_id)}：{Name(issue.target_key)}の利用位置から出口へ到達できません。";
            if (issue.kind=="exposure")
                return $"{Scenario(issue.scenario_id)}：{Name(issue.target_key)}と危険領域が {issue.area_m2:F3} m² 重なります。";
            return "追加の確認事項があります。";
        }
        public static string Note(string value) => value switch
        {
            "No placed exit: escape routes are not evaluated" => "出口が設定されていないため、避難経路は未評価です。",
            "No bed or seat: personal exposure and escape are not evaluated" => "ベッド・椅子がないため、人体への危険と避難経路は未評価です。",
            _ => "未評価の項目があります。"
        };
        static string NamesInText(string value)
        {
            foreach (var name in new[] { "Ceiling Light", "Ceiling light", "TV stand", "TV Unit", "Shelf", "Bed", "Table", "Chair" })
                value=value.Replace(name,Name(name));
            return value;
        }
        public static string Advice(string value)
        {
            // Safety messages are shown using the structured issues above, without duplicates.
            if (string.IsNullOrEmpty(value) || value.StartsWith("exposure:") || value.StartsWith("escape_blocked:") ||
                value.StartsWith("No placed exit:") || value.StartsWith("No bed or seat:")) return null;
            var text=NamesInText(value);
            var match=Regex.Match(text,@"^(.+) clearance overlaps occupied area \(([^ ]+) cell units squared\)$");
            if (match.Success) return $"{match.Groups[1]}の利用空間が家具と重なっています（{match.Groups[2]} セル²）。";
            match=Regex.Match(text,@"^(\d+) free cells are unreachable from the exit$");
            if (match.Success) return $"出口から到達できない空き領域が {match.Groups[1]} セルあります。";
            match=Regex.Match(text,@"^(.+) to (.+) distance ([^ ]+) is outside \[([^,]+), ([^\]]+)\]$");
            if (match.Success) return $"{match.Groups[1]}と{match.Groups[2]}の距離（{match.Groups[3]} セル）が設定範囲（{match.Groups[4]}～{match.Groups[5]} セル）から外れています。";
            match=Regex.Match(text,@"^(.+) to (.+) distance ([^ ]+) is outside conversation range$");
            if (match.Success) return $"{match.Groups[1]}と{match.Groups[2]}の距離（{match.Groups[3]} セル）が会話用の設定範囲から外れています。";
            if (text.EndsWith(": preferred face is not aligned with a solid wall"))
                return text.Replace(": preferred face is not aligned with a solid wall","：対象の面が開口部のない壁に沿っていません。");
            if (text=="Furniture mass is visually off-center") return "家具全体の重心が部屋の中央から偏っています。";
            UnityEngine.Debug.LogWarning("Untranslated evaluation detail: "+value);
            return "追加の配置上の注意があります（詳細はログを参照）。";
        }
        public static string EvaluationText(Evaluation result)
        {
            var safety=result.safety;
            var text=new StringBuilder();
            text.AppendLine(safety.Summary);
            text.AppendLine($"危険領域との重複面積：{safety.overlap_area_m2:F3} m²（各シナリオの合計）");
            text.AppendLine($"避難できない判定：{safety.failed_route_checks} / {safety.route_checks} 件");
            text.AppendLine($"配置の不自然さ・使いにくさ：{result.natural_cost:F3}（小さいほど良好）");
            foreach (var issue in safety.issues ?? Array.Empty<SafetyIssue>()) text.AppendLine("・"+Issue(issue));
            foreach (var note in safety.unassessed ?? Array.Empty<string>()) text.AppendLine(Note(note));
            text.AppendLine("\n窓との距離（安全な境界距離を示すものではありません）");
            if (safety.window_distances==null || safety.window_distances.Length==0) text.AppendLine("対象となる窓とベッド・椅子の組合せはありません。");
            foreach (var distance in safety.window_distances ?? Array.Empty<WindowDistance>())
                text.AppendLine($"{Name(distance.window_key)}から{Name(distance.target_key)}：{distance.distance_m:F2} m");
            text.AppendLine("\n対策の記録");
            foreach (var m in result.mitigations ?? Array.Empty<Mitigation>())
                text.AppendLine(m.kind=="window" ? $"{Name(m.key)}：飛散防止フィルム {Protection(m.film)}／就寝時のカーテン {Protection(m.curtains)}" :
                    $"{Name(m.key)}：{Restraint(m.restraint)}／設置状態 {Installation(m.installation_confirmed)}");
            text.AppendLine("対策の記録によって危険領域が消えることはありません。");
            text.AppendLine("\n評価の内訳（小さいほど良好）");
            foreach (var term in result.breakdown ?? Array.Empty<ScoreTerm>()) text.AppendLine($"{ScoreName(term.name)}：{term.value:F3}");
            text.AppendLine("\n配置上の注意（1セル＝25cm）");
            foreach (var violation in result.violations ?? Array.Empty<string>())
            {
                string advice=Advice(violation);
                if (advice!=null) text.AppendLine("・"+advice);
            }
            return text.ToString();
        }
        public static string ServerError(string detail)
        {
            if (string.IsNullOrEmpty(detail)) return "処理に失敗しました。もう一度お試しください。";
            if (detail.Contains("Place all furniture")) return "評価する前に、すべての家具を配置してください。";
            if (detail.Contains("Furniture overlap")) return "家具同士が重なっています。配置を調整してください。";
            if (detail.Contains("Door clearance blocked")) return "ドア前に家具が重なっています。配置を調整してください。";
            if (detail.Contains("out of room bounds")) return "部屋の外にはみ出している家具があります。配置を調整してください。";
            return "サーバーで処理できませんでした。配置や接続先を確認して再実行してください。";
        }
    }
}
