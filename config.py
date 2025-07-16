OPENAI_KEY = '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'
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_GPT_INSTANCE = 10
OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
style = 'DISC'
task_content = ''

trigger_proactive_DISC_interval = 20
trigger_proactive_SCOL_interval = 35
trigger_proactive_INDW_interval = 50

memory_divide = 180 #180s内作为短期记忆

context_range = 1 #默认上下文范围为1

short_memory_selected_range_response_DISC = 20 #选取短期记忆中最近20秒的内容
short_memory_selected_num_response_DISC = 2 #如果对话和态度均为空，挑选最近2条对话记录
long_memory_selected_num_response_DISC = 3 #长期记忆中与用户提问内容最相关的3条对话

short_memory_selected_range_proactive_chat_DISC = 30 #选取短期记忆中最近30秒的内容
short_memory_selected_num_proactive_chat_DISC = 3 #如果对话和态度均为空，挑选最近3条对话记录
long_memory_selected_num_proactive_chat_DISC = 3 #长期记忆中与用户提问内容最相关的3条对话

short_memory_selected_range_response_SCOL = 30 #选取短期记忆中最近30秒的内容
short_memory_selected_num_response_SCOL = 3 #如果对话和态度均为空，挑选最近3条对话记录
long_memory_selected_num_response_SCOL = 3 #长期记忆中与用户提问内容最相关的3条对话

short_memory_selected_range_proactive_chat_SCOL = 45 #选取短期记忆中最近45秒的内容
short_memory_selected_num_proactive_chat_SCOL = 3 #如果对话和态度均为空，挑选最近3条对话记录
long_memory_selected_num_proactive_chat_SCOL = 5 #长期记忆中与用户提问内容最相关的5条对话

short_memory_selected_range_response_INDW = 30 #选取短期记忆中最近30秒的内容
short_memory_selected_num_response_INDW = 3 #如果对话和态度均为空，挑选最近3条对话记录
long_memory_selected_num_response_INDW = 3 #长期记忆中与用户提问内容最相关的3条对话

short_memory_selected_range_proactive_chat_INDW = 45 #选取短期记忆中最近45秒的内容
short_memory_selected_num_proactive_chat_INDW = 3 #如果对话和态度均为空，挑选最近3条对话记录
long_memory_selected_num_proactive_chat_INDW = 5 #长期记忆中与用户提问内容最相关的5条对话