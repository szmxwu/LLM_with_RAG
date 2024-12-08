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

def extract_images_from_slide(slide_xml):
    """提取幻灯片中引用的所有图像"""
    images = set()  # 使用集合避免重复图像
    tree = ET.ElementTree(ET.fromstring(slide_xml))
    root = tree.getroot()
    
    # 遍历XML中所有的图像元素
    for image in root.iter():
        if 'blipFill' in image.tag:  # 这是图像的标签
            for blip in image.iter():
                print(blip.tag,blip.attrib)
                #blip.attrib={'{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed': 'rId2'}
                attrib=list(blip.attrib.keys())
                if not attrib:
                    continue
                attrib=attrib[0]
                if 'blip' in blip.tag and 'embed' in attrib:
                    images.add(blip.attrib[attrib])  # 获取图像的引用
    return images

def split_pptx(file_path):
    # 获取文件的大小（字节）
    file_size = os.path.getsize(file_path)
    
    # 判断文件大小是否小于100MB
    if file_size <= 100 * 1024 * 1024:
        return [file_path]
    
    # 获取文件名和扩展名
    file_name, file_extension = os.path.splitext(file_path)
    
    # 创建拆分后的文件夹
    output_folder = f"{file_name}_split"
    os.makedirs(output_folder, exist_ok=True)
    
    # 解压pptx文件
    with zipfile.ZipFile(file_path, 'r') as pptx_zip:
        # 获取PPTX文件内部的所有文件
        file_list = pptx_zip.namelist()
        
        # 拆分文件的索引
        part_number = 1
        current_size = 0
        temp_files = []
        
        
        # 创建新的Zip文件用于拆分
        with zipfile.ZipFile(os.path.join(output_folder, f"{file_name}_{part_number}.pptx"), 'w') as current_zip:
            image_references = set()  # 用于存储当前拆分文件需要的图像
            
            # 遍历文件列表，处理每个文件
            for item in file_list:
                # 检查文件是否为幻灯片（在ppt/slides/目录下）
                if item.startswith('ppt/slides/'):
                    # 获取幻灯片文件内容
                    file_data = pptx_zip.read(item)
                    slide_xml = file_data.decode('utf-8')  # 转换为字符串
                    
                    # 提取该幻灯片引用的所有图像
                    slide_images = extract_images_from_slide(slide_xml)
                    image_references.update(slide_images)  # 添加到当前拆分文件需要的图像集
                
                    # 将幻灯片文件写入当前zip文件
                    current_zip.writestr(item, file_data)
                    current_size += len(file_data)

                # 处理图像文件（ppt/media/目录下）
                elif item.startswith('ppt/media/') and item.split('/')[-1] in image_references:
                    # 获取图像文件内容
                    file_data = pptx_zip.read(item)
                    # 将图像文件写入到当前拆分文件的ppt/media/文件夹中
                    current_zip.writestr(item, file_data)
                    current_size += len(file_data)

            # 判断是否超出100MB
            if current_size > 100 * 1024 * 1024:
                # 关闭当前的Zip文件并开启一个新的
                current_zip.close()
                part_number += 1
                current_size = 0
                # part_folder = os.path.join(output_folder, f"{file_name}_{part_number}")
                # os.makedirs(part_folder, exist_ok=True)
                current_zip = zipfile.ZipFile(os.path.join(output_folder, f"{file_name}_{part_number}.pptx"), 'w')
                
            # 返回拆分后的文件路径列表
        split_files = [os.path.join(output_folder, f"{file_name}_{i}.pptx") for i in range(1, part_number + 1)]
    
    return split_files

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
    file_path = 'F:\\big_pptx\\神经科特征性脑影像荟萃.pptx' # 替换为你的文件路径
    result = split_pptx(file_path)
    if isinstance(result, list):
        print("文件被拆分为以下文件：")
        for r in result:
            print(r)
    else:
        print("文件大小小于100MB，直接返回文件地址：", result)

