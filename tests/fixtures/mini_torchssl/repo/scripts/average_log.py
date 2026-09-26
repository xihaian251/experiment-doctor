"""Synthetic stand-in for TorchSSL's scripts/average_log.py (see the real script).

Trimmed to the rules the adapter cites: the completeness gate on the literal
'1048000 iteration' string (:23 in the original), the group key, and the
round(np.mean, 2) +/- round(np.std, 2) cell writer.
"""
# gate
#     if '1048000 iteration' in line:
#         continue_flag = True
# membership loop
# statics = sorted(statics.items())
# final_res = {}
# for s in statics:
#     exp_name = '_'.join(s[0].split('_')[:-1])
#     if s[1]['Finish'] == False:
#         print(s[0], 'is not finished')
#         continue
#     if exp_name not in final_res:
#         tmp = {'Top1_1': [s[1]['Top1_1']*100],
#             'Top1_20': [s[1]['Top1_20']*100],
#             'Top1_50': [s[1]['Top1_50']*100],
#             'Top5_1': [s[1]['Top5_1']*100],
#             'Top5_20': [s[1]['Top5_20']*100],
#             'Top5_50': [s[1]['Top5_50']*100],
#             'BestAcc': [s[1]['BestAcc']*100]}
#         final_res[exp_name] = tmp
#     else:
#         final_res[exp_name]['BestAcc'].append(s[1]['BestAcc']*100)
# cell writer
# worksheet.write(algs.index(alg)+1,j+1,str(round(np.mean(v[show_acc[i]]),2))+u"±"+str(round(np.std(v[show_acc[i]]),2)))
