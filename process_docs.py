import os
from PyPDF2 import PdfReader, PdfWriter
import fitz  # PyMuPDF
from PIL import Image
from pptx import Presentation
from docx import Document
import io
import zipfile
import shutil
from xml.etree import ElementTree as ET
from pathlib import Path
import subprocess
def split_pptx(file_path, max_size=100 * 1024 * 1024):
    """
    将超过100M的PPTX文件转换为pdf再分拆上传。
    """
    slide_size = os.path.getsize(file_path)
    if slide_size <= max_size :
        return [file_path]
    pdfpath="cache//"+os.path.splitext(os.path.basename(file_path))[0]+".pdf"
    cmd=["soffice", "--headless", "--convert-to", "pdf:writer_pdf_Export",
            file_path, "--outdir","cache"]
    try:
        subprocess.run(cmd,capture_output=True)
    except Exception as e:
        print(e)
    if os.path.exists(pdfpath):
        print("pdf convert succeeded.")
        filepath=pdfpath
    else:
        print("pdf convert failed ")
        return ""
    slide_size = os.path.getsize(filepath)
    if slide_size > max_size :     
        return split_pdf(file_path)
    else:
        return [filepath]

def split_pdf(file_path, max_size=100 * 1024 * 1024):
    # 获取文件名和扩展名
    file_name = os.path.basename(file_path)
    file_name_without_extension, file_extension = os.path.splitext(file_name)
    split_file_list=[]
    # 检查文件扩展名是否为 .pdf
    if file_extension.lower() != '.pdf':
        print("文件不是 PDF 格式")
        return None
    
    # 获取文件大小
    file_size = os.path.getsize(file_path)
    
    # 检查文件大小是否大于 100MB
    if file_size <= max_size:
        print("文件大小不超过 100MB，无需拆分")
        return [file_path]
    
    # 打开 PDF 文件
    with open(file_path, 'rb') as pdf_file:
        reader = PdfReader(pdf_file)
        num_pages = len(reader.pages)
        
        # 初始化变量
        current_page = 0
        current_size = 0
        file_counter = 1
        
        while current_page < num_pages:
            writer = PdfWriter()
            while current_page < num_pages and current_size + reader.pages[current_page].get_size() <= max_size:
                writer.add_page(reader.pages[current_page])
                current_size += reader.pages[current_page].get_size()
                current_page += 1
            
            # 生成新的文件名
            new_file_name = f"{file_name_without_extension}_{file_counter}{file_extension}"
            new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
            
            # 写入新的 PDF 文件
            with open(new_file_path, 'wb') as new_pdf_file:
                writer.write(new_pdf_file)
            split_file_list.append(new_file_path)
            # 重置当前大小
            current_size = 0
            file_counter += 1
            #重叠一页
            if current_page>0:
                current_page-=1
            
    print("PDF 文件拆分完成")
    return split_file_list



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
    print(f"Page {page_number} from {pdf_path} saved as {image_path}")
    return image_path

if __name__ == '__main__':
# 示例用法
    # split_pdf('5格-艾放射诊断学（第六版）\\1-（超高清晰版）格-艾放射诊断学（第六版）上卷.pdf', 'output_directory')
    # pdf_path = "example.pdf"
    # page_number = 2  # 要截取的页码
    # image_path = "output_page_2.png"

    # pdf_page_to_image(pdf_path, page_number, image_path)
    file_path = 'F:\\big_pptx\\骨关节缺血坏死.pptx' # 替换为你的文件路径
    result = split_pptx(file_path)
    print(result)
