import time
from langchain_openai import ChatOpenAI
from multiprocessing import Pool

base_url="http://192.0.0.193:9997/v1"
model_name = 'qwen2.5-instruct'  # 模型UID

llm = ChatOpenAI(
            base_url=base_url,
            model=model_name,
            api_key="EMPTY",
    )

prompt="""
请写一篇关于人工智能对于社会劳动就业影响的论文的大纲，并对第一章写出细纲,对第一节写出详细内容
"""
def test_model(max_tokens):
    start_time = time.time()
    response=llm.invoke(prompt,config={"max_tokens": max_tokens})
    
    end_time = time.time()

    # 计算总耗时
    total_time = end_time - start_time
    # print(n,response.choices[0].message.content)
    return total_time, response.response_metadata['token_usage']['completion_tokens']



def measure_token_generation_speed(num_concurrent_requests,max_tokens):

    # 创建一个进程池，指定进程数量为4
    with Pool(processes=num_concurrent_requests) as pool:
        # 使用map或者apply_async提交任务
        # 使用map会更加简洁和方便，因为我们只需要收集结果
        # 准备参数列表
        args=[max_tokens]*num_concurrent_requests
        results = pool.map(test_model,args)

    # 计算平均耗时和平均生成速度
    # print(results)
    avg_time = sum(result[0] for result in results) / len(results)
    avg_tokens_generated = sum(result[1] for result in results) / len(results)
    tokens_per_second = avg_tokens_generated / avg_time if avg_time > 0 else 0

    print(f"Average time per request: {avg_time:.4f} seconds")
    print(f"Average tokens generated: {avg_tokens_generated:.2f}")
    print(f"Tokens per second (TPS): {tokens_per_second:.2f}")

if __name__ == "__main__":
    # 参数设置
    
    num_concurrent_requests = 8  # 并发请求数
    max_tokens=1000 #最长输出token
    # 运行测试
    measure_token_generation_speed(num_concurrent_requests,max_tokens)
