import os
from PyPDF2 import PdfReader, PdfWriter
import fitz  # PyMuPDF
from PIL import Image
from pptx import Presentation
from docx import Document
import io
import uuid
import shutil
import subprocess
from io import BytesIO
import logging
class RAGFlowPptParser(object):
    def __init__(self):
        super().__init__()

    def __extract(self, shape):
        if shape.shape_type == 19:
            tb = shape.table
            rows = []
            for i in range(1, len(tb.rows)):
                rows.append("; ".join([tb.cell(
                    0, j).text + ": " + tb.cell(i, j).text for j in range(len(tb.columns)) if tb.cell(i, j)]))
            return "\n".join(rows)

        if shape.has_text_frame:
            return shape.text_frame.text

        if shape.shape_type == 6:
            texts = []
            for p in sorted(shape.shapes, key=lambda x: (x.top // 10, x.left)):
                t = self.__extract(p)
                if t:
                    texts.append(t)
            return "\n".join(texts)

    def __call__(self, fnm, content, callback=None):
        ppt = Presentation(fnm) if isinstance(
            fnm, str) else Presentation(
            BytesIO(fnm))
        self.total_page = len(ppt.slides)
        for i, slide in enumerate(ppt.slides):
            if i < 0:
                continue
            if i >= 1024:
                break
            texts = []
            for shape in sorted(
                    slide.shapes, key=lambda x: ((x.top if x.top is not None else 0) // 10, x.left)):
                try:
                    txt = self.__extract(shape)
                    if txt:
                        texts.append(txt)
                except Exception as e:
                    logging.exception(e)
                page_text="\n".join(texts)
                if content in page_text:
                    return i+1
        return None

async def convert_pptx(file):
    """
    将PPT文件尽可能转化成word上传，保持内容的连续性。
    """
    english_path = str(uuid.uuid4()) + ".pptx"
    dest=open(f"{english_path}","wb")
    content=await file.read()
    dest.write(content)
    dest.close()
    # 使用pptx2md将pptx转换为markdown
    md_file = english_path.replace(".pptx", ".md")
    result=None
    try:
        subprocess.run(["pptx2md", english_path,"-o", md_file], check=True)

        # 使用pandoc将markdown转换为docx
        docx_file = os.path.basename(file.filename).replace(".pptx", ".docx")
        subprocess.run(
            ["pandoc", md_file, "-o", docx_file], check=True)

        # 删除中间生成的markdown文件
        os.remove(md_file)
        if os.path.exists('img'):
            shutil.rmtree('img')
        result=docx_file
    except:
        shutil.copyfile(file_path, os.path.join("cache",os.path.basename(file_path)))
        dest=open(os.path.join("cache",file.filename),"wb")
        dest.write(content)
        dest.close()
        result=file
    #删除中间文件
    os.remove(english_path)
    return [result]

def get_pdf_size(pdf_writer):
    """获取当前PDF内容的大小（估算）"""
    temp_file = BytesIO()
    pdf_writer.write(temp_file)
    return len(temp_file.getvalue()) / (1024 * 1024)  # 返回大小（MB）


async def split_pdf(file):
    # 检查文件是否为PDF格式
    if not file.filename.lower().endswith('.pdf'):
        return "错误：文件不是PDF格式"

    # 获取文件大小，检查是否需要拆分
    content=await file.read()
    if file.size <= 100*1024 * 1024:
        dest=open(f"cache//{file.filename}")
        dest.write(content)
        dest.close()
        return [file]  # 如果文件小于等于100MB，拷贝到cache中并返回路径

    # 打开PDF文件
    print("正准备读取文件：")
    pdf_stream=BytesIO(content)
    print("正在读取文件：",pdf_stream)
    pdf_reader = PdfReader(pdf_stream)
    total_pages = len(pdf_reader.pages)
    print("文件一共有:",total_pages)
    sub_files = []  # 用于存储拆分后的文件路径
    pdf_writer = PdfWriter()
    base_name = os.path.splitext(os.path.basename(file.filename))[0]
    sub_file_index = 1
    last_page = None  # 用于存储上一页，保证重叠一页

    # 遍历每一页，逐步拆分
    for page_num in range(total_pages):
        # 如果是拆分后的第一个子文件，直接添加
        if last_page is None:
            pdf_writer.add_page(pdf_reader.pages[page_num])
        else:
            # 如果是后续子文件，确保重叠一页
            pdf_writer.add_page(last_page)
            pdf_writer.add_page(pdf_reader.pages[page_num])

        # 获取当前子文件的大小
        current_size = get_pdf_size(pdf_writer)

        # 如果当前子文件超过了100MB，则保存当前子文件并重新开始
        if current_size > 100:
            sub_file_path = f"cache//{base_name}_{sub_file_index}.pdf"
            with open(sub_file_path, 'wb') as sub_file:
                pdf_writer.write(sub_file)
            sub_files.append(sub_file_path)

            # 清空pdf_writer并开始新的一页
            pdf_writer = PdfWriter()

            # 保留当前页面作为下一个子文件的第一页
            last_page = pdf_reader.pages[page_num]
            sub_file_index += 1
        else:
            last_page = pdf_reader.pages[page_num]

    # 最后一个子文件
    if len(pdf_writer.pages) > 0:
        sub_file_path = f"cache//{base_name}_{sub_file_index}.pdf"
        with open(sub_file_path, 'wb') as sub_file:
            pdf_writer.write(sub_file)
        sub_files.append(sub_file_path)
    print("完成拆分文件:",sub_files)
    return sub_files






def split_docx(file_path, max_size=100 * 1024 * 1024):
    # 获取文件名和目录
    dir_name, file_name = os.path.split(file_path)
    base_name, ext = os.path.splitext(file_name)
    
    # 读取原始 DOCX 文件
    doc = Document(file_path)
    
    # 初始化变量
    current_doc = Document()
    current_size = 0
    file_count = 1
    output_file_path = os.path.join(dir_name, f"{base_name}_{file_count}{ext}")
    
    # 创建一个内存缓冲区
    buffer = io.BytesIO()
    
    for para in doc.paragraphs:
        # 将段落添加到当前文档
        current_doc.add_paragraph(para.text)
        
        # 将当前文档写入内存缓冲区
        buffer.seek(0)
        current_doc.save(buffer)
        buffer.seek(0)
        
        # 计算当前文档的大小
        current_size = buffer.getbuffer().nbytes
        
        # 如果当前文档大小超过限制，则保存当前文档并创建新文档
        if current_size > max_size:
            current_doc.save(output_file_path)
            current_doc = Document()
            file_count += 1
            output_file_path = os.path.join(dir_name, f"{base_name}_{file_count}{ext}")
            current_doc.add_paragraph(para.text)
            
            # 重新计算当前文档的大小
            buffer.seek(0)
            current_doc.save(buffer)
            buffer.seek(0)
            current_size = buffer.getbuffer().nbytes
    
    # 保存最后一个文档
    if current_size > 0:
        current_doc.save(output_file_path)
    
    # 清理内存缓冲区
    buffer.close()


def pdf_page_to_image(pdf_path, page_number):
    # 打开PDF文件
    try:
        pdf_document = fitz.open(pdf_path)
    except:
        print(pdf_path + "不存在")
        return None
    
    # 确保页码在正确范围内
    if page_number < 1 or page_number > pdf_document.page_count:
        print(page_number + " 页码错误")
        return None
    
    # 获取对应页码的页面 (fitz 的页码从0开始，所以要减1)
    page = pdf_document.load_page(page_number - 1)
    
    # 转换页面为PixMap对象
    mat=fitz.Matrix(2,2)
    pix = page.get_pixmap(matrix=mat,clip=None,alpha=False)
    
    # 将PixMap对象转换为Image对象
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    
    # 保存图片
    filename=os.path.splitext(pdf_path)[0]
    image_path=f"{filename}_{page_number}.png"
    img.save(image_path)
    
    # 关闭PDF文件
    pdf_document.close()
    # print(f"Page {page_number} from {pdf_path} saved as {image_path}")
    return image_path






    
if __name__ == '__main__':
# 示例用法
    # split_pdf('5格-艾放射诊断学（第六版）\\1-（超高清晰版）格-艾放射诊断学（第六版）上卷.pdf', 'output_directory')
    # pdf_path = "example.pdf"
    # page_number = 2  # 要截取的页码
    # image_path = "output_page_2.png"

    # pdf_page_to_image(pdf_path, page_number, image_path)
    # file_path = "H:\\output_directory\\pdf\\肿瘤影像诊断图谱.pdf"# 替换为你的文件路径
    file_path="H:\\output_directory\\1-（超高清晰版）格-艾放射诊断学（第六版）上卷.pdf_1.docx"
    # result = split_pdf(file_path)
    # print(result)
    input_docx = 'test.docx'  # 输入的 Word 文档路径
    output_docx = 'output_document.docx'  # 输出的 Word 文档路径


