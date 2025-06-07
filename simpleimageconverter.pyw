#V2.2 Image Orientation fix 7/6/2025
#Program no longer forces landscape orientation and you can manually rotate images before operations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

# Function to check and install missing dependencies
def check_and_install(package):
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

def install_dependencies():
    packages = ['Pillow', 'pillow-heif', 'tkinterdnd2', 'rawpy', 'realesrgan']
    
    # Use ThreadPoolExecutor to install packages in parallel
    with ThreadPoolExecutor() as executor:
        executor.map(check_and_install, packages)

install_dependencies()

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
import os
from PIL import Image, ImageTk
from PIL.ExifTags import TAGS
import threading
from pathlib import Path
import rawpy
import pillow_heif

# Enable HEIF support
pillow_heif.register_heif_opener()

class ImageThumbnail:
    def __init__(self, file_path):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.processed = False
        self.thumbnail = None
        self.thumbnail_widget = None
        self.manual_rotation = 0
        
    def create_thumbnail(self, size=(150, 120)):
        try:
            img = self.load_and_orient_image()
            if img is None:
                return None
                
            # Apply manual rotation if any
            if hasattr(self, 'manual_rotation') and self.manual_rotation != 0:
                img = img.rotate(-self.manual_rotation, expand=True)  # Negative because PIL rotates counter-clockwise
            
            img.thumbnail(size, Image.Resampling.LANCZOS)
            self.thumbnail = ImageTk.PhotoImage(img)
            return self.thumbnail
        except Exception as e:
            print(f"Error creating thumbnail for {self.filename}: {e}")
            return None

    def get_exif_data(self):
        """Extract EXIF data from the original image"""
        try:
            if self.file_path.lower().endswith(('.cr2', '.nef', '.arw', '.dng', '.raf')):
                # RAW files - EXIF handling is limited
                return None
            else:
                img = Image.open(self.file_path)
                return img.getexif()
        except Exception as e:
            print(f"Error extracting EXIF from {self.filename}: {e}")
            return None
    
    def load_and_orient_image(self):
        """Load image and apply proper orientation from EXIF data"""
        try:
            if self.file_path.lower().endswith(('.cr2', '.nef', '.arw', '.dng', '.raf')):
                # Handle RAW files
                with rawpy.imread(self.file_path) as raw:
                    rgb = raw.postprocess()
                    img = Image.fromarray(rgb)
            else:
                # Handle regular image files
                img = Image.open(self.file_path)
                
                # Apply EXIF orientation if available
                try:
                    exif_data = img.getexif()
                    if exif_data is not None:
                        orientation = exif_data.get(274)  # 274 is the EXIF orientation tag
                        if orientation:
                            if orientation == 3:
                                img = img.rotate(180, expand=True)
                            elif orientation == 6:
                                img = img.rotate(270, expand=True)
                            elif orientation == 8:
                                img = img.rotate(90, expand=True)
                except Exception as e:
                    print(f"Could not apply EXIF orientation for {self.filename}: {e}")
            
            return img
        except Exception as e:
            print(f"Error loading image {self.filename}: {e}")
            return None
        
    def rotate_image_manual(self, degrees):
        """Manually rotate the image by specified degrees"""
        self.manual_rotation = getattr(self, 'manual_rotation', 0) + degrees
        self.manual_rotation = self.manual_rotation % 360
        
        # Refresh thumbnail
        if hasattr(self, 'thumbnail_widget') and self.thumbnail_widget:
            self.thumbnail_widget.refresh_thumbnail()

class ImageFrame(tk.Frame):
    def __init__(self, parent, on_remove_callback):
        super().__init__(parent)
        self.on_remove_callback = on_remove_callback
        self.image_data = None
        self.setup_ui()
        
    def setup_ui(self):
        # Image label (larger thumbnail) - using pixels instead of characters
        self.image_label = tk.Label(self, bg="lightgray", width=160, height=120)
        self.image_label.pack(padx=5, pady=5)
        
        # Remove button (X) overlayed on image - smaller and positioned better
        self.remove_btn = tk.Button(
            self.image_label, text="×", font=("Arial", 8, "bold"),
            fg="white", bg="red", width=1, height=1,
            command=self.remove_image, bd=0
        )
        self.remove_btn.place(x=5, y=5)
        
        # Filename label
        self.filename_label = tk.Label(self, text="", font=("Arial", 9), wraplength=150)
        self.filename_label.pack(pady=(0, 5))
        
        # Status indicator (bottom right of image)
        self.status_label = tk.Label(self.image_label, text="", font=("Arial", 16), bg="lightgray")
        self.status_label.place(relx=1.0, rely=1.0, anchor="se", x=-5, y=-5)
        
    def set_image(self, image_data):
        self.image_data = image_data
        thumbnail = image_data.create_thumbnail()
        if thumbnail:
            self.image_label.config(image=thumbnail, width=160, height=120)
            self.image_label.image = thumbnail  # Keep a reference
        self.filename_label.config(text=image_data.filename)

        self.setup_rotation_buttons()
        
    def remove_image(self):
        if self.on_remove_callback and self.image_data:
            self.on_remove_callback(self.image_data)
            
    def mark_processed(self):
        self.status_label.config(text="✓", fg="green")
        if self.image_data:
            self.image_data.processed = True

    def setup_rotation_buttons(self):
        """Add rotation buttons to the image frame"""
        # Rotate left button
        self.rotate_left_btn = tk.Button(
            self.image_label, text="↶", font=("Arial", 12, "bold"),
            fg="white", bg="blue", width=2, height=1,
            command=self.rotate_left, bd=0
        )
        self.rotate_left_btn.place(x=25, y=5)
        
        # Rotate right button
        self.rotate_right_btn = tk.Button(
            self.image_label, text="↷", font=("Arial", 12, "bold"),
            fg="white", bg="blue", width=2, height=1,
            command=self.rotate_right, bd=0
        )
        self.rotate_right_btn.place(x=50, y=5)
    
    def rotate_left(self):
        """Rotate image 90 degrees counter-clockwise"""
        if self.image_data:
            self.image_data.rotate_image_manual(-90)
    
    def rotate_right(self):
        """Rotate image 90 degrees clockwise"""
        if self.image_data:
            self.image_data.rotate_image_manual(90)
    
    def refresh_thumbnail(self):
        """Refresh the thumbnail display"""
        if self.image_data:
            thumbnail = self.image_data.create_thumbnail()
            if thumbnail:
                self.image_label.config(image=thumbnail)
                self.image_label.image = thumbnail  # Keep a reference

class BaseTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.images = []
        self.output_dir = None
        self.setup_ui()
        self.setup_drag_drop()
        
    def setup_ui(self):
        # Drop zone
        self.drop_frame = tk.Frame(self, bg="lightblue", height=80)
        self.drop_frame.pack(fill=tk.X, padx=10, pady=5)
        
        drop_label = tk.Label(
            self.drop_frame, 
            text="Drag and drop images anywhere on this tab",
            bg="lightblue", font=("Arial", 12)
        )
        drop_label.pack(expand=True)
        
        # Scrollable thumbnail area
        self.setup_thumbnail_area()
        
        # Controls frame
        self.controls_frame = tk.Frame(self)
        self.controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Output directory selection
        self.output_btn = tk.Button(
            self.controls_frame, text="Select Output Directory",
            command=self.select_output_directory
        )
        self.output_btn.pack(side=tk.LEFT, padx=5)
        
        self.output_label = tk.Label(
            self.controls_frame, text="Output: (default folder will be created)",
            font=("Arial", 9), fg="gray"
        )
        self.output_label.pack(side=tk.LEFT, padx=10)
        
        # EXIF preservation checkbox
        self.preserve_exif = tk.BooleanVar(value=True)
        self.exif_checkbox = tk.Checkbutton(
            self.controls_frame, text="Preserve EXIF data",
            variable=self.preserve_exif
        )
        self.exif_checkbox.pack(side=tk.LEFT, padx=10)
        
        # Clear selections button
        self.clear_btn = tk.Button(
            self.controls_frame, text="Clear All",
            command=self.clear_all_images, bg="orange", fg="white"
        )
        self.clear_btn.pack(side=tk.RIGHT, padx=5)
        
        # Process button
        self.process_btn = tk.Button(
            self.controls_frame, text="Process Images",
            command=self.process_images, bg="green", fg="white"
        )
        self.process_btn.pack(side=tk.RIGHT, padx=5)
        
        # Add tab-specific controls
        self.setup_controls()
        
    def setup_thumbnail_area(self):
        # Canvas and scrollbar for thumbnails
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.canvas = tk.Canvas(canvas_frame, height=150)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=scrollbar.set)
        
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Frame inside canvas for thumbnails
        self.thumbnails_frame = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.thumbnails_frame, anchor="nw")
        
    def setup_drag_drop(self):
        # Enable drag and drop for the entire tab
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        
        # Also enable for child widgets to ensure coverage
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)
        
    def get_default_output_dir(self):
        # Override in subclasses to return tab-specific folder name
        return "processed"
        
    def select_output_directory(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir = directory
            self.output_label.config(
                text=f"Output: {os.path.basename(directory)}/",
                fg="black"
            )
        else:
            self.output_dir = None
            self.output_label.config(
                text="Output: (default folder will be created)",
                fg="gray"
            )
        
    def setup_controls(self):
        # Override in subclasses
        pass
        
    def on_drop(self, event):
        files = event.data.split()
        for file_path in files:
            file_path = file_path.strip('{}')  # Remove braces if present
            if self.is_valid_image(file_path):
                self.add_image(file_path)
                
    def is_valid_image(self, file_path):
        valid_extensions = {
            '.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', 
            '.webp', '.heic', '.heif', '.cr2', '.nef', '.arw', 
            '.dng', '.raf', '.gif'
        }
        return Path(file_path).suffix.lower() in valid_extensions
        
    def add_image(self, file_path):
        image_data = ImageThumbnail(file_path)
        self.images.append(image_data)
        
        # Create thumbnail frame
        thumb_frame = ImageFrame(self.thumbnails_frame, self.remove_image)
        thumb_frame.set_image(image_data)
        thumb_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        image_data.thumbnail_widget = thumb_frame
        
        # Update canvas scroll region
        self.thumbnails_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
    def remove_image(self, image_data):
        if image_data in self.images:
            self.images.remove(image_data)
            if image_data.thumbnail_widget:
                image_data.thumbnail_widget.destroy()
            
            # Update canvas scroll region
            self.thumbnails_frame.update_idletasks()
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def clear_all_images(self):
        """Remove all images from the current tab"""
        # Create a copy of the list to avoid modifying while iterating
        images_to_remove = list(self.images)
        
        for image_data in images_to_remove:
            self.remove_image(image_data)
        
        # Update canvas scroll region
        self.thumbnails_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            
    def process_images(self):
        if not self.images:
            messagebox.showwarning("No Images", "Please add images first.")
            return
            
        # Determine output directory
        if self.output_dir:
            output_dir = self.output_dir
        else:
            # Create default folder next to the first image
            first_image_dir = os.path.dirname(self.images[0].file_path)
            default_folder = self.get_default_output_dir()
            output_dir = os.path.join(first_image_dir, default_folder)
            
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
            
        # Disable process button during processing
        self.process_btn.config(state=tk.DISABLED, text="Processing...")
        
        # Process in separate thread
        threading.Thread(
            target=self.process_images_thread,
            args=(output_dir,),
            daemon=True
        ).start()
        
    def process_images_thread(self, output_dir):
        processed_count = 0
        for image_data in self.images:
            try:
                self.process_single_image(image_data, output_dir)
                # Update UI in main thread
                self.after(0, image_data.thumbnail_widget.mark_processed)
                processed_count += 1
            except Exception as e:
                print(f"Error processing {image_data.filename}: {e}")
                
        # Show completion message and re-enable button
        self.after(0, lambda: messagebox.showinfo("Complete", f"Processed {processed_count} images successfully!"))
        self.after(0, lambda: self.process_btn.config(state=tk.NORMAL, text="Process Images"))
        
    def process_single_image(self, image_data, output_dir):
        # Override in subclasses
        pass

    def save_with_exif(self, img, output_path, format_name, image_data, **kwargs):
        """Save image with optional EXIF preservation"""
        try:
            if self.preserve_exif.get():
                # Get original EXIF data
                exif_data = image_data.get_exif_data()
                if exif_data and format_name in ['JPEG', 'TIFF']:
                    # Save with EXIF data for supported formats
                    img.save(output_path, format=format_name, exif=exif_data, **kwargs)
                else:
                    # Save without EXIF if not supported by format or no EXIF data
                    img.save(output_path, format=format_name, **kwargs)
            else:
                # Save without EXIF
                img.save(output_path, format=format_name, **kwargs)
        except Exception as e:
            # Fallback: save without EXIF if there's an error
            print(f"Warning: Could not preserve EXIF for {image_data.filename}, saving without EXIF: {e}")
            img.save(output_path, format=format_name, **kwargs)

class ConvertTab(BaseTab):
    def get_default_output_dir(self):
        return "converted"
        
    def setup_controls(self):
        tk.Label(self.controls_frame, text="Convert to:").pack(side=tk.LEFT, padx=5)
        
        # Expanded format list with popular formats first
        formats = [
            # Popular formats
            "JPEG", "PNG", "WEBP", "TIFF",
            # Less common but supported formats
            "BMP", "GIF", "TGA", "PPM", "PBM", "PGM",
            "PCX", "ICNS", "ICO", "IM", "MSP", "SGI",
            "SPIDER", "XBM", "XPM"
        ]
        
        self.format_var = tk.StringVar(value="JPEG")
        format_combo = ttk.Combobox(
            self.controls_frame, textvariable=self.format_var,
            values=formats, state="readonly"
        )
        format_combo.pack(side=tk.LEFT, padx=5)
        
        # Quality control for lossy formats
        tk.Label(self.controls_frame, text="Quality:").pack(side=tk.LEFT, padx=5)
        self.quality_var = tk.StringVar(value="95")
        self.quality_entry = tk.Entry(self.controls_frame, textvariable=self.quality_var, width=6)
        self.quality_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.controls_frame, text="(for JPEG/WEBP)", font=("Arial", 8), fg="gray").pack(side=tk.LEFT, padx=2)
        
    def process_single_image(self, image_data, output_dir):
            img = image_data.load_and_orient_image()
            if img is None:
                raise Exception("Could not load image")
                
            # Apply manual rotation if any
            if hasattr(image_data, 'manual_rotation') and image_data.manual_rotation != 0:
                img = img.rotate(-image_data.manual_rotation, expand=True)
                
            format_name = self.format_var.get()
            
            # Convert mode if necessary
            if format_name == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                # Convert to RGB for JPEG
                if img.mode == 'P':
                    img = img.convert('RGBA')
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                img = background
            elif format_name == 'BMP' and img.mode in ('RGBA', 'LA'):
                # BMP doesn't support transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
                
            # Generate output filename
            base_name = Path(image_data.filename).stem
            
            # File extensions mapping
            ext_map = {
                'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'TIFF': '.tiff',
                'BMP': '.bmp', 'GIF': '.gif', 'TGA': '.tga', 'PPM': '.ppm',
                'PBM': '.pbm', 'PGM': '.pgm', 'PCX': '.pcx', 'ICNS': '.icns',
                'ICO': '.ico', 'IM': '.im', 'MSP': '.msp', 'SGI': '.sgi',
                'SPIDER': '.spi', 'XBM': '.xbm', 'XPM': '.xpm'
            }
            
            ext = ext_map.get(format_name, f'.{format_name.lower()}')
            output_path = os.path.join(output_dir, f"{base_name}{ext}")
            
            # Save with appropriate parameters
            save_kwargs = {}
            if format_name in ['JPEG', 'WEBP']:
                quality = int(self.quality_var.get()) if self.quality_var.get() else 95
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            
            self.save_with_exif(img, output_path, format_name, image_data, **save_kwargs)
            print(f"Converted: {image_data.filename} -> {os.path.basename(output_path)}")

class ResizeTab(BaseTab):
    def get_default_output_dir(self):
        return "resized"
        
    def setup_controls(self):
        # Resize method
        tk.Label(self.controls_frame, text="Method:").pack(side=tk.LEFT, padx=5)
        
        self.method_var = tk.StringVar(value="Pixels")
        method_combo = ttk.Combobox(
            self.controls_frame, textvariable=self.method_var,
            values=["Pixels", "Percentage", "File Size Limit"],
            state="readonly"
        )
        method_combo.pack(side=tk.LEFT, padx=5)
        method_combo.bind('<<ComboboxSelected>>', self.on_method_change)
        
        # Dynamic input fields frame
        self.input_frame = tk.Frame(self.controls_frame)
        self.input_frame.pack(side=tk.LEFT, padx=10)
        
        # Initialize with pixels method
        self.setup_pixels_inputs()
        
    def on_method_change(self, event=None):
        # Clear existing inputs
        for widget in self.input_frame.winfo_children():
            widget.destroy()
            
        method = self.method_var.get()
        if method == "Pixels":
            self.setup_pixels_inputs()
        elif method == "Percentage":
            self.setup_percentage_inputs()
        elif method == "File Size Limit":
            self.setup_filesize_inputs()
            
    def setup_pixels_inputs(self):
        # Width
        tk.Label(self.input_frame, text="Width:").pack(side=tk.LEFT, padx=5)
        self.width_var = tk.StringVar(value="800")
        tk.Entry(self.input_frame, textvariable=self.width_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # Height
        tk.Label(self.input_frame, text="Height:").pack(side=tk.LEFT, padx=5)
        self.height_var = tk.StringVar(value="600")
        tk.Entry(self.input_frame, textvariable=self.height_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # Maintain aspect ratio
        self.maintain_aspect = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.input_frame, text="Maintain aspect ratio",
            variable=self.maintain_aspect
        ).pack(side=tk.LEFT, padx=5)
        
    def setup_percentage_inputs(self):
        tk.Label(self.input_frame, text="Scale %:").pack(side=tk.LEFT, padx=5)
        self.scale_var = tk.StringVar(value="50")
        tk.Entry(self.input_frame, textvariable=self.scale_var, width=8).pack(side=tk.LEFT, padx=5)
        
    def setup_filesize_inputs(self):
        tk.Label(self.input_frame, text="Max Size (KB):").pack(side=tk.LEFT, padx=5)
        self.filesize_var = tk.StringVar(value="500")
        tk.Entry(self.input_frame, textvariable=self.filesize_var, width=8).pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.input_frame, text="Quality:").pack(side=tk.LEFT, padx=5)
        self.quality_var = tk.StringVar(value="85")
        tk.Entry(self.input_frame, textvariable=self.quality_var, width=6).pack(side=tk.LEFT, padx=5)
        
    def process_single_image(self, image_data, output_dir):
            img = image_data.load_and_orient_image()
            if img is None:
                raise Exception("Could not load image")
                
            # Apply manual rotation if any
            if hasattr(image_data, 'manual_rotation') and image_data.manual_rotation != 0:
                img = img.rotate(-image_data.manual_rotation, expand=True)
                
            method = self.method_var.get()
            
            if method == "Pixels":
                width = int(self.width_var.get()) if self.width_var.get() else img.width
                height = int(self.height_var.get()) if self.height_var.get() else img.height
                
                if self.maintain_aspect.get():
                    img.thumbnail((width, height), Image.Resampling.LANCZOS)
                else:
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                    
            elif method == "Percentage":
                scale = float(self.scale_var.get()) / 100 if self.scale_var.get() else 1.0
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
            elif method == "File Size Limit":
                # Try different qualities until file size is acceptable
                target_size_kb = int(self.filesize_var.get()) if self.filesize_var.get() else 500
                quality = int(self.quality_var.get()) if self.quality_var.get() else 85
                
                # Convert to RGB if necessary for JPEG compression
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Binary search for optimal quality
                import io
                min_quality, max_quality = 10, quality
                best_quality = quality
                
                for _ in range(10):  # Max 10 iterations
                    test_quality = (min_quality + max_quality) // 2
                    buffer = io.BytesIO()
                    
                    # Use EXIF if preserving and available
                    save_kwargs = {'format': 'JPEG', 'quality': test_quality, 'optimize': True}
                    if self.preserve_exif.get():
                        exif_data = image_data.get_exif_data()
                        if exif_data:
                            save_kwargs['exif'] = exif_data
                    
                    img.save(buffer, **save_kwargs)
                    size_kb = len(buffer.getvalue()) / 1024
                    
                    if size_kb <= target_size_kb:
                        best_quality = test_quality
                        min_quality = test_quality + 1
                    else:
                        max_quality = test_quality - 1
                        
                    if min_quality > max_quality:
                        break
                
                # Use the best quality found
                quality = best_quality
                
            # Generate output filename
            base_name = Path(image_data.filename).stem
            original_ext = Path(image_data.filename).suffix
            ext = original_ext if method != "File Size Limit" else '.jpg'
            output_path = os.path.join(output_dir, f"{base_name}_resized{ext}")
            
            # Save
            if method == "File Size Limit":
                self.save_with_exif(img, output_path, 'JPEG', image_data, quality=quality, optimize=True)
            else:
                # Determine format from extension
                format_name = 'JPEG' if ext.lower() in ['.jpg', '.jpeg'] else img.format or 'PNG'
                self.save_with_exif(img, output_path, format_name, image_data)
                
            print(f"Resized: {image_data.filename} -> {os.path.basename(output_path)}")

class CompressTab(BaseTab):
    def get_default_output_dir(self):
        return "web-optimized"
        
    def setup_controls(self):
        # Output format - expanded list
        tk.Label(self.controls_frame, text="Format:").pack(side=tk.LEFT, padx=5)
        
        # Popular compression formats first
        formats = [
            "WEBP", "JPEG", "PNG", "TIFF",
            # Additional formats that support compression
            "BMP", "TGA", "PPM", "PGM", "PCX"
        ]
        
        self.format_var = tk.StringVar(value="WEBP")
        format_combo = ttk.Combobox(
            self.controls_frame, textvariable=self.format_var,
            values=formats, state="readonly"
        )
        format_combo.pack(side=tk.LEFT, padx=5)
        
        # Quality
        tk.Label(self.controls_frame, text="Quality:").pack(side=tk.LEFT, padx=5)
        self.quality_var = tk.StringVar(value="80")
        tk.Entry(self.controls_frame, textvariable=self.quality_var, width=8).pack(side=tk.LEFT, padx=5)
        
        # Max width/height for web
        tk.Label(self.controls_frame, text="Max Size (px):").pack(side=tk.LEFT, padx=5)
        self.max_size_var = tk.StringVar(value="1920")
        tk.Entry(self.controls_frame, textvariable=self.max_size_var, width=8).pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.controls_frame, text="(maintains aspect ratio)", font=("Arial", 8), fg="gray").pack(side=tk.LEFT, padx=5)
        
    def process_single_image(self, image_data, output_dir):
            img = image_data.load_and_orient_image()
            if img is None:
                raise Exception("Could not load image")
                
            # Apply manual rotation if any
            if hasattr(image_data, 'manual_rotation') and image_data.manual_rotation != 0:
                img = img.rotate(-image_data.manual_rotation, expand=True)
                
            # Resize if larger than max size (maintaining aspect ratio)
            max_size = int(self.max_size_var.get()) if self.max_size_var.get() else 1920
            
            # Find the larger dimension and scale based on that
            if img.width > max_size or img.height > max_size:
                if img.width > img.height:
                    # Width is larger, scale based on width
                    ratio = max_size / img.width
                    new_width = max_size
                    new_height = int(img.height * ratio)
                else:
                    # Height is larger, scale based on height
                    ratio = max_size / img.height
                    new_height = max_size
                    new_width = int(img.width * ratio)
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            format_name = self.format_var.get()
            
            # Convert mode if necessary
            if format_name == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
                # Convert to RGB for JPEG
                if img.mode == 'P':
                    img = img.convert('RGBA')
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                img = background
                
            # Generate output filename
            base_name = Path(image_data.filename).stem
            
            # File extensions mapping
            ext_map = {
                'WEBP': '.webp', 'JPEG': '.jpg', 'PNG': '.png', 'TIFF': '.tiff',
                'BMP': '.bmp', 'TGA': '.tga', 'PPM': '.ppm', 'PGM': '.pgm',
                'PCX': '.pcx'
            }
            
            ext = ext_map.get(format_name, f'.{format_name.lower()}')
            output_path = os.path.join(output_dir, f"{base_name}{ext}")
            
            # Save with compression
            quality = int(self.quality_var.get()) if self.quality_var.get() else 80
            save_kwargs = {}
            
            if format_name in ['JPEG', 'WEBP']:
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            elif format_name == 'PNG':
                save_kwargs['optimize'] = True
                # PNG compression level (0-9, where 9 is maximum compression)
                save_kwargs['compress_level'] = min(9, max(0, int((100 - quality) / 10)))
            elif format_name == 'TIFF':
                save_kwargs['compression'] = 'tiff_lzw'  # Use LZW compression for TIFF
            
            self.save_with_exif(img, output_path, format_name, image_data, **save_kwargs)
            print(f"Compressed: {image_data.filename} -> {os.path.basename(output_path)}")

class UpscaleTab(BaseTab):
    def get_default_output_dir(self):
        return "upscaled"

    def setup_controls(self):
        # Upscale method
        tk.Label(self.controls_frame, text="Method:").pack(side=tk.LEFT, padx=5)
        self.method_var = tk.StringVar(value="Real-ESRGAN")
        ttk.Combobox(
            self.controls_frame, textvariable=self.method_var,
            values=["Real-ESRGAN", "LANCZOS"], state="readonly"
        ).pack(side=tk.LEFT, padx=5)

        # Scale selector
        tk.Label(self.controls_frame, text="Scale:").pack(side=tk.LEFT, padx=5)
        self.scale_var = tk.StringVar(value="2")
        ttk.Combobox(
            self.controls_frame, textvariable=self.scale_var,
            values=["2", "4"], state="readonly"
        ).pack(side=tk.LEFT, padx=5)

        # Denoise option
        self.denoise_after = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.controls_frame,
            text="Denoise after upscaling",
            variable=self.denoise_after
        ).pack(side=tk.LEFT, padx=10)

    def process_single_image(self, image_data, output_dir):
            img = image_data.load_and_orient_image()
            if img is None:
                raise Exception("Could not load image")
                
            # Apply manual rotation if any
            if hasattr(image_data, 'manual_rotation') and image_data.manual_rotation != 0:
                img = img.rotate(-image_data.manual_rotation, expand=True)

            method = self.method_var.get()
            scale = int(self.scale_var.get())

            # Apply upscaling
            if method == "Real-ESRGAN":
                try:
                    from realesrgan import RealESRGAN
                    import torch

                    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                    model = RealESRGAN(device, scale=scale)
                    model.load_weights(f'RealESRGAN_x{scale}plus.pth', download=True)

                    img = model.predict(img)
                except ImportError:
                    print("Real-ESRGAN not installed. Falling back to LANCZOS.")
                    method = "LANCZOS"
                except Exception as e:
                    print(f"Real-ESRGAN error: {e}. Falling back to LANCZOS.")
                    method = "LANCZOS"

            if method == "LANCZOS":
                new_size = (img.width * scale, img.height * scale)
                img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Denoise after upscaling if enabled
            if self.denoise_after.get():
                try:
                    import cv2
                    import numpy as np
                    img_np = np.array(img)
                    # Apply bilateral filter
                    img_np = cv2.bilateralFilter(img_np, d=9, sigmaColor=75, sigmaSpace=75)
                    img = Image.fromarray(img_np)
                    print("Applied OpenCV denoising")
                except ImportError:
                    print("OpenCV not installed. Skipping denoising.")
                except Exception as e:
                    print(f"Denoising error: {e}")

            # Save output
            base_name = Path(image_data.filename).stem
            ext = Path(image_data.filename).suffix
            output_path = os.path.join(output_dir, f"{base_name}_upscaled{ext}")
            format_name = img.format or 'PNG'
            self.save_with_exif(img, output_path, format_name, image_data)

            print(f"Upscaled: {image_data.filename} -> {os.path.basename(output_path)}")

class ImageProcessorApp:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Simple Image Converter")
        self.root.geometry("1200x700")
        self.setup_ui()
        
    def setup_ui(self):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.convert_tab = ConvertTab(self.notebook)
        self.resize_tab = ResizeTab(self.notebook)
        self.compress_tab = CompressTab(self.notebook)
        self.upscale_tab = UpscaleTab(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.convert_tab, text="Convert")
        self.notebook.add(self.resize_tab, text="Resize")
        self.notebook.add(self.compress_tab, text="Compress")
        self.notebook.add(self.upscale_tab, text="Upscale")
        
        # Menu bar
        self.setup_menu()
        
    def setup_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Add Images", command=self.add_images)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
    def add_images(self):
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[
                ("All Images", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif *.webp *.heic *.heif *.cr2 *.nef *.arw *.dng *.raf *.gif"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("PNG files", "*.png"),
                ("RAW files", "*.cr2 *.nef *.arw *.dng *.raf"),
                ("All files", "*.*")
            ]
        )
        
        current_tab = self.notebook.select()
        tab_widget = self.notebook.nametowidget(current_tab)
        
        for file_path in files:
            if tab_widget.is_valid_image(file_path):
                tab_widget.add_image(file_path)
                
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ImageProcessorApp()
    app.run()
