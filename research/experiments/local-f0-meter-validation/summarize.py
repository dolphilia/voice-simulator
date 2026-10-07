"""自己回復資格と日本語の回帰診断を混同しない終了判断。"""
from campaign import LocalBudget, RESULT, read, save


def main():
    with LocalBudget().job('audit','開発選択・確認・局所感度・資格不足を集計',1000000):
        development=read(RESULT/'development-selection.json');confirmation=read(RESULT/'confirmation.json')
        assert development['selected_method']==confirmation['selected_method']
        selected=development['selected_method'];confirmed=confirmation['selected_method_confirmed']
        regress=read(RESULT/'regression-summary.json')
        reasons=[]
        if selected is None:reasons.append('開発12条件をすべて通過する方式がない')
        elif not confirmed:reasons.append('開発で固定した方式が確認12条件の必須条件を満たさない')
        if regress['completed']!=93:reasons.append('日本語回帰診断の欠損')
        accepted=selected if confirmed and regress['completed']==93 else None
        save(RESULT/'summary.json',{'development':development['methods'],'confirmation':confirmation['methods'],
            'selected_from_development':selected,'qualified_procedural_signal_method':accepted,'rejection_reasons':reasons,
            'regression':regress,'current_f0_objective_replaced':False,'previous_results_rejudged':False,
            'japanese_measurement_qualified':False,'human_perception_qualified':False,'quality_certified':False,
            'all_requirements_met':False,'next_waveform_objective_comparison_supported':accepted is not None,
            'interpretation':'既知信号の工学診断。内部LF0との整合や確認側のみの好成績から方式を救済しない。',
            'unresolved':['日本語の音素境界・有声判定資格','未知文共有制御','局所タイミング・閉鎖・開放・摩擦・声質',
                          '日本語非ニューラル知覚資格','独立最終品質確認']})
        print({'selected':selected,'qualified':accepted,'reasons':reasons},flush=True)

if __name__=='__main__':main()
