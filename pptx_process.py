import os
import zipfile
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET
import re

def get_file_size(file_path):
    """获取文件大小，单位为字节"""
    return os.path.getsize(file_path)


def calculate_slide_size(slide_file, rels_dir, media_dir):
    """
    计算幻灯片文件和其关联资源的总大小。
    :param slide_file: 幻灯片 XML 文件路径
    :param rels_dir: 幻灯片关系文件所在目录
    :param media_dir: 媒体文件所在目录
    :return: 幻灯片及其关联资源的总大小（字节）
    """
    total_size = get_file_size(slide_file)

    # 找到对应的关系文件
    slide_name = Path(slide_file).stem  # slide1, slide2, ...
    rels_file = Path(rels_dir) / f"{slide_name}.xml.rels"
    if rels_file.exists():
        tree = ET.parse(rels_file)
        root = tree.getroot()
        for rel in root:
            if not rel.tag.endswith("Relationship"): 
                continue
            target = rel.attrib.get("Target", "")
            if target.startswith("../media/"):
                media_file = Path(media_dir) / Path(target).name
                if media_file.exists():
                    total_size += get_file_size(media_file)

    return total_size

def natural_sort_key(key):
    """为自然排序提取数字部分"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(key))]

def split_pptx(file_path, max_size=100 * 1024 * 1024):
    """
    拆分 PPTX 文件，将其分成不大于指定大小的小文件。
    音频和视频资源会被抛弃。
    """
    base_name, ext = os.path.splitext(file_path)
    output_dir = f"{base_name}_split"
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)  # 清理旧的拆分目录
    os.makedirs(output_dir, exist_ok=True)

    with zipfile.ZipFile(file_path, "r") as pptx_zip:
        # 解压 PPTX 文件内容到临时目录
        temp_dir = f"{base_name}_temp"
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        pptx_zip.extractall(temp_dir)

        # 获取必要的路径
        slides_dir = os.path.join(temp_dir, "ppt/slides")
        rels_dir = os.path.join(temp_dir, "ppt/slides/_rels")
        media_dir = os.path.join(temp_dir, "ppt/media")
        slides = sorted(Path(slides_dir).glob("slide*.xml"), key=natural_sort_key)
        
        # 初始化拆分逻辑
        part_index = 1
        current_size = 0
        current_parts = []
        part_files = []

        def copy_required_files(part_dir):
            """
            拷贝必需的文件和目录到目标目录。
            """
            exclude_files=[]
            if not os.path.exists(part_dir):
                os.makedirs(part_dir)  # 创建目标目录如果它不存在

            for root, dirs, files in os.walk(temp_dir):
                # 复制子目录
                for dir_name in dirs:
                    src_dir_path = os.path.join(root, dir_name)
                    dst_dir_path = os.path.join(part_dir, os.path.relpath(src_dir_path, temp_dir))
                    os.makedirs(dst_dir_path, exist_ok=True)

                # 复制文件，排除指定文件
                for file in files:
                    if re.search("slide\d+.xml|.jpg|jpeg|png|wav|mpeg|mp3",file):
                        continue
                    src_file_path = os.path.join(root, file)
                    dst_file_path = os.path.join(part_dir, os.path.relpath(src_file_path, temp_dir))
                    shutil.copy2(src_file_path, dst_file_path)  # 使用shutil.copy2保留文件的元数据
           
        def create_pptx_part(output_dir):
            """将当前部分内容打包为一个新的 PPTX 文件"""
            nonlocal current_parts, part_index, current_size
            part_name = os.path.join(output_dir, f"{base_name}_part{part_index}.pptx")
            part_dir = f"{temp_dir}_part{part_index}"

            # 创建新目录并拷贝必要的文件
            os.makedirs(part_dir, exist_ok=True)
            copy_required_files(part_dir)


            # 拷贝当前部分的幻灯片和关联资源
            for slide_file in current_parts:
                shutil.copy(slide_file, os.path.join(part_dir, "ppt/slides"))
                slide_name = Path(slide_file).stem
                rels_file = Path(rels_dir) / f"{slide_name}.xml.rels"
                if rels_file.exists():
                    rels_target = os.path.join(part_dir, "ppt/slides/_rels")
                    os.makedirs(rels_target, exist_ok=True)
                    shutil.copy(rels_file, rels_target)

                # 拷贝关联的媒体资源
                if rels_file.exists():
                    tree = ET.parse(rels_file)
                    root = tree.getroot()
                    for rel in root:
                        if not rel.tag.endswith("Relationship"): 
                            continue
                        target = rel.attrib.get("Target", "")
                        if target.startswith("../media/"):
                            media_file = Path(media_dir) / Path(target).name
                            if media_file.exists():
                                media_target = os.path.join(part_dir, "ppt/media")
                                os.makedirs(media_target, exist_ok=True)
                                shutil.copy(media_file, media_target)

            # 打包为 PPTX 文件
            with zipfile.ZipFile(part_name, "w", zipfile.ZIP_DEFLATED) as zipf:
                for folder_name, subfolders, filenames in os.walk(part_dir):
                    for filename in filenames:
                        file_path = os.path.join(folder_name, filename)
                        arcname = os.path.relpath(file_path, part_dir)
                        zipf.write(file_path, arcname)

            # 更新拆分状态
            shutil.rmtree(part_dir)
            part_files.append(part_name)
            current_parts = []
            current_size = 0
            part_index += 1

        # 遍历每个幻灯片
        for slide_file in slides:
            slide_size = calculate_slide_size(slide_file, rels_dir, media_dir)
            if current_size + slide_size > max_size and current_parts:
                create_pptx_part(output_dir)
            current_parts.append(slide_file)
            current_size += slide_size
            print(slide_file.name,"大小:%.2fM" %(slide_size/1024/1024),"总大小:%.2fM" %(current_size/1024/1024))

        # 创建最后一部分
        if current_parts:
            create_pptx_part(output_dir)

        # 清理临时目录
        shutil.rmtree(temp_dir)

    return part_files




# 使用示例
if __name__ == "__main__":
    file_path = "F:\\big_pptx\\骨关节缺血坏死.pptx"
    split_files = split_pptx(file_path)
    print(f"拆分后的文件：{split_files}")
