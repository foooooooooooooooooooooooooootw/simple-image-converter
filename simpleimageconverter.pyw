#V1.8 19/5/25
#Added tabs for different image manipulation purposes
#Added errors for the messagebox if a file fails to convert
#Added a resize tab to resize images
#fixed .dng file conversion issue (it only converted the thumbnail not the actual image)
#fixed .arw files not generating thumbnails but it can be optimized further
#TODO: complete upscale tab

import subprocess
import sys

# Function to check and install missing dependencies
def check_and_install(package):
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

def install_dependencies():
    packages = ['Pillow', 'pillow-heif', 'tkinterdnd2', 'pillow-avif-plugin', 'rawpy','opencv-python', 'opencv-contrib-python','numpy']
    for package in packages:
        check_and_install(package)

install_dependencies()

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES  # Drag-and-drop support
from PIL import Image, ImageDraw, ImageTk, ImageFont, ImageFilter, ImageStat
from pillow_heif import register_heif_opener
import rawpy
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures
import psutil
import cv2
import numpy as np
import urllib.request
try:
    import pillow_avif 
    AVIF_SUPPORTED = True
except ImportError:
    AVIF_SUPPORTED = False

# Check for FFmpeg availability
def check_ffmpeg():
    """Check if FFmpeg is installed and available on the PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

FFMPEG_AVAILABLE = check_ffmpeg()

# Register HEIF opener with Pillow to handle HEIC files
register_heif_opener()

# Updated FORMAT_OPTIONS with popular formats on top
POPULAR_FORMATS = {
    'PNG': {'ext': 'png', 'supports_quality': False},
    'JPEG': {'ext': 'jpeg', 'supports_quality': True},
    'BMP': {'ext': 'bmp', 'supports_quality': False},
    'TIFF': {'ext': 'tiff', 'supports_quality': False},
    'GIF': {'ext': 'gif', 'supports_quality': False},
    'ICO': {'ext': 'ico', 'supports_quality': False},
    'WEBP': {'ext': 'webp', 'supports_quality': True},
    'HEIF': {'ext': 'heif', 'supports_quality': True} if 'pillow_heif' in sys.modules else None,
    'AVIF': {'ext': 'avif', 'supports_quality': True} if AVIF_SUPPORTED else None,
    'JXL': {'ext': 'jxl', 'supports_quality': True} if FFMPEG_AVAILABLE else None
}

ADDITIONAL_FORMATS = {
    'EPS': {'ext': 'eps', 'supports_quality': False},
    'IM': {'ext': 'im', 'supports_quality': False},
    'MSP': {'ext': 'msp', 'supports_quality': False},
    'PCX': {'ext': 'pcx', 'supports_quality': False},
    'PPM': {'ext': 'ppm', 'supports_quality': False},
    'SGI': {'ext': 'sgi', 'supports_quality': False},
    'SPIDER': {'ext': 'spi', 'supports_quality': False},
    'TGA': {'ext': 'tga', 'supports_quality': False},
    'XBM': {'ext': 'xbm', 'supports_quality': False},
    'PALM': {'ext': 'palm', 'supports_quality': False},
    'PDF': {'ext': 'pdf', 'supports_quality': False},  # Requires an additional PDF reader
    'PSD': {'ext': 'psd', 'supports_quality': False},
    'XPM': {'ext': 'xpm', 'supports_quality': False},
    'DIB': {'ext': 'dib', 'supports_quality': False}
}

# Combine into a single FORMAT_OPTIONS for the dropdown
FORMAT_OPTIONS = {**POPULAR_FORMATS, **ADDITIONAL_FORMATS}

if FFMPEG_AVAILABLE:
    FORMAT_OPTIONS['JXL'] = {'ext': 'jxl', 'supports_quality': True}

FORMAT_OPTIONS = {k: v for k, v in FORMAT_OPTIONS.items() if v is not None}

# Helper functions for JPEG XL conversion using FFmpeg
def save_as_jxl(input_image_path, output_path, quality=100):
    """Convert an image to JPEG XL format using FFmpeg."""
    quality_flag = f"-q:v {quality}"  # FFmpeg quality flag
    subprocess.run(["ffmpeg", "-i", input_image_path, quality_flag, output_path], check=True)

def open_jxl_as_image(jxl_path):
    """Open a JPEG XL image by converting it to a temporary PNG using FFmpeg."""
    temp_png = jxl_path + ".temp.png"
    try:
        subprocess.run(["ffmpeg", "-i", jxl_path, temp_png], check=True)
        image = Image.open(temp_png)
    finally:
        if os.path.exists(temp_png):
            os.remove(temp_png)
    return image

def open_raw_as_image(raw_path):
    print(f"Using rawpy to open {raw_path}")
    with rawpy.imread(raw_path) as raw:
        rgb_array = raw.postprocess()
    return Image.fromarray(rgb_array)

def download_model(url, model_name, model_dir='models'):
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, model_name)
    if not os.path.exists(model_path):
        print(f"Downloading model: {model_name}")
        urllib.request.urlretrieve(url, model_path)
    else:
        print(f"Model already exists: {model_name}")
    return model_path

class ImageConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Image Converter")

        # Set fixed size limits for the window to prevent unintended expansion
        self.root.minsize(600, 600)
        self.root.maxsize(1000, 800)
        
        # Initialize variables
        self.selected_files = []
        self.resize_files = []
        self.upscale_files = []
        self.thumbnails = []  # Store thumbnail references to prevent garbage collection
        self.output_format = tk.StringVar(value='PNG')
        self.output_directory = tk.StringVar()
        self.quality = tk.IntVar(value=85)  # Default JPEG quality
        self.thumbnail_labels = {}
        self.thumbnail_size = 150  # Default thumbnail size
        self.columns = 3  # Default number of columns for thumbnails
        self.loading_thread = None  # Track the thumbnail loading thread
        self.lock = threading.Lock()  # Lock to prevent concurrent thread issues

        # Set up drag-and-drop
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.handle_dropped_files)

        # Set up GUI
        self.setup_gui()

    def setup_gui(self):
        # Create a notebook (tab control)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)

        # Create frames for each tab
        self.convert_tab = ttk.Frame(self.notebook)

        # Add tabs
        self.notebook.add(self.convert_tab, text="Convert")

        # Move the existing GUI elements to convert_tab
        self.build_convert_tab()
        self.build_resize_tab()
        self.build_upscale_tab()
        
    def build_convert_tab(self):
        # File selection buttons
        tk.Button(self.convert_tab, text="Select Images", command=self.select_files).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(self.convert_tab, text="Clear Selections", command=self.clear_selections).grid(row=0, column=1, padx=5, pady=5)

        # Output format selection
        tk.Label(self.convert_tab, text="Output Format").grid(row=1, column=0, padx=5, pady=5)
        format_menu = ttk.Combobox(self.convert_tab, textvariable=self.output_format, values=list(FORMAT_OPTIONS.keys()), state="readonly")
        format_menu.grid(row=1, column=1, padx=5, pady=5)
        format_menu.bind("<<ComboboxSelected>>", self.toggle_quality_option)

        # Quality setting for JPEG as a slider
        self.quality_label = tk.Label(self.convert_tab, text="Quality (1-100):")
        self.quality_label.grid(row=2, column=0, padx=5, pady=5)

        self.quality_slider = tk.Scale(self.convert_tab, variable=self.quality, from_=1, to=100, orient=tk.HORIZONTAL)
        self.quality_slider.grid(row=2, column=1, padx=5, pady=5)
        self.toggle_quality_option()

        # Bind arrow keys to control the slider on the main window
        self.convert_tab.bind("<Left>", self.decrease_quality)
        self.convert_tab.bind("<Right>", self.increase_quality)

        # Output directory selection
        tk.Button(self.convert_tab, text="Select Output Directory", command=self.select_output_directory).grid(row=3, column=0, padx=5, pady=5)
        self.output_dir_display = tk.Label(self.convert_tab, text="No output directory selected. (Will create default)")
        self.output_dir_display.grid(row=3, column=1, padx=5, pady=5)

        # Image thumbnail preview area
        self.thumbnail_frame = tk.Frame(self.convert_tab, bg="white")
        self.thumbnail_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=10, sticky='nsew')

        # Make the row and column expandable
        self.convert_tab.grid_rowconfigure(4, weight=1)  # Make row 4 expandable
        self.convert_tab.grid_columnconfigure(0, weight=1)  # Make column 0 expandable
        self.convert_tab.grid_columnconfigure(1, weight=1)  # Make column 1 expandable

        self.canvas = tk.Canvas(self.thumbnail_frame, bg="white")
        self.scrollbar = ttk.Scrollbar(self.thumbnail_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="white")
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Use pack for better control over resizing
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Convert button
        tk.Button(self.convert_tab, text="Convert Images", command=self.convert_images_threaded).grid(row=5, column=0, columnspan=2, pady=10)

        # Track window resizing to dynamically adjust thumbnail size and canvas width
        self.convert_tab.bind("<Configure>", self.debounce_resize_event)

    def build_resize_tab(self):
        self.resize_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.resize_tab, text="Resize")

        # Select Images and Clear Selections Buttons
        tk.Button(self.resize_tab, text="Select Images", command=self.select_resize_files).grid(row=0, column=0, padx=5, pady=5)
        clear_button = ttk.Button(self.resize_tab, text="Clear Selections", command=self.clear_resize_selections)
        clear_button.grid(row=0, column=1, columnspan=2, pady=(10, 5))


        # Resize Mode Dropdown (Pixel or Percentage)
        self.resize_mode = tk.StringVar(value="Percentage")
        tk.Label(self.resize_tab, text="Resize Mode:").grid(row=1, column=0, padx=5, pady=5)
        self.resize_mode_dropdown = tk.OptionMenu(self.resize_tab, self.resize_mode, "Pixels", "Percentage", command=self.toggle_resize_mode)
        self.resize_mode_dropdown.grid(row=1, column=1, padx=5, pady=5)

        # Width and Height Entry Fields (set default text to the current image size)
        self.resize_width_label = tk.Label(self.resize_tab, text="Width:")
        self.resize_width_label.grid(row=2, column=0, sticky="e", padx=5, pady=5)

        self.resize_width = tk.Entry(self.resize_tab)
        self.resize_width.grid(row=2, column=1, padx=5, pady=5)

        self.resize_height_label = tk.Label(self.resize_tab, text="Height:")
        self.resize_height_label.grid(row=3, column=0, sticky="e", padx=5, pady=5)

        self.resize_height = tk.Entry(self.resize_tab)
        self.resize_height.grid(row=3, column=1, padx=5, pady=5)

        # Keep Aspect Ratio Checkbox
        self.keep_aspect = tk.BooleanVar(value=True)
        self.keep_aspect_check = tk.Checkbutton(self.resize_tab, text="Keep Aspect Ratio", variable=self.keep_aspect)
        self.keep_aspect_check.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        # Percentage Slider (initially hidden)
        self.percentage_slider = tk.Scale(
            self.resize_tab,
            from_=1,
            to=300,
            orient=tk.HORIZONTAL,
            label="Percentage",
            state=tk.DISABLED,
            command=self.update_resized_dimensions  # No lambda needed
        )
        self.percentage_slider.grid(row=5, column=0, columnspan=2, padx=5, pady=5)

        # Output Directory Selection
        tk.Button(self.resize_tab, text="Select Output Directory", command=self.select_output_directory).grid(row=6, column=0, padx=5, pady=5)
        self.output_dir_label_resize = tk.Label(self.resize_tab, text="No output directory selected.")
        self.output_dir_label_resize.grid(row=6, column=1, padx=5, pady=5)

        # Thumbnail frame (adjust size, shrink down to fit within the window better)
        self.thumbnail_frame_resize = tk.Frame(self.resize_tab, bg="white", height=250)  # Adjusted size
        self.thumbnail_frame_resize.grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

        self.resize_canvas = tk.Canvas(self.thumbnail_frame_resize, bg="white")
        self.resize_scrollbar = ttk.Scrollbar(self.thumbnail_frame_resize, orient="vertical", command=self.resize_canvas.yview)
        self.resize_scrollable_frame = tk.Frame(self.resize_canvas, bg="white")
        self.resize_scrollable_frame.bind("<Configure>", lambda e: self.resize_canvas.configure(scrollregion=self.resize_canvas.bbox("all")))

        self.resize_canvas.create_window((0, 0), window=self.resize_scrollable_frame, anchor="nw")
        self.resize_canvas.configure(yscrollcommand=self.resize_scrollbar.set)

        self.resize_canvas.pack(side="left", fill="both", expand=True)
        self.resize_scrollbar.pack(side="right", fill="y")

        # Original and resized size labels
        self.original_size_label = tk.Label(self.resize_tab, text="Original: —")
        self.original_size_label.grid(row=8, column=0, padx=5, pady=5)

        self.resized_size_label = tk.Label(self.resize_tab, text="Resized: —")
        self.resized_size_label.grid(row=8, column=1, padx=5, pady=5)

        # Resize Button
        tk.Button(self.resize_tab, text="Resize Images", command=self.resize_images_threaded).grid(row=8, column=0, columnspan=2, pady=10)

        # Adjust column/row weights to ensure resizing behaves well
        self.resize_tab.grid_rowconfigure(7, weight=1)  # Make the thumbnail area expandable
        self.resize_tab.grid_columnconfigure(0, weight=1)
        self.resize_tab.grid_columnconfigure(1, weight=1)

        # Set initial visibility
        self.toggle_resize_mode("Percentage")  # Ensure the correct elements are visible initially

        # This function will clear the placeholder text when the user starts typing
        def clear_placeholder_text(event, entry, placeholder):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)

        # This function will reset the placeholder text if the field is left empty
        def restore_placeholder_text(event, entry, placeholder):
            if entry.get() == "":
                entry.insert(0, placeholder)

        # Add event listeners for the width/height fields
        self.resize_width.bind("<FocusIn>", lambda event: clear_placeholder_text(event, self.resize_width, "Width"))
        self.resize_width.bind("<FocusOut>", lambda event: restore_placeholder_text(event, self.resize_width, "Width"))
        self.resize_height.bind("<FocusIn>", lambda event: clear_placeholder_text(event, self.resize_height, "Height"))
        self.resize_height.bind("<FocusOut>", lambda event: restore_placeholder_text(event, self.resize_height, "Height"))

        self.resize_tab.drop_target_register(DND_FILES)
        self.resize_tab.dnd_bind('<<Drop>>', self.handle_resize_dropped_files)

        self.bind_arrow_keys()  # Bind arrow keys for fine control of the slider

    def build_upscale_tab(self):
        self.upscale_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.upscale_tab, text="Upscale")

        # File selection buttons
        button_frame = tk.Frame(self.upscale_tab)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Select Images", command=self.select_upscale_files).pack(side="left", padx=10)
        tk.Button(button_frame, text="Clear Selections", command=self.clear_upscale_selections).pack(side="left", padx=10)
        tk.Button(button_frame, text="Upscale", command=self.start_upscale_thread).pack(side="left", padx=10)

        # Option for upscale mode
        self.upscale_mode = tk.StringVar(value="Factor")
        mode_frame = tk.Frame(self.upscale_tab)
        mode_frame.pack(pady=5)

        tk.Radiobutton(mode_frame, text="By Factor", variable=self.upscale_mode, value="Factor", command=self.toggle_upscale_mode).pack(side="left", padx=10)
        tk.Radiobutton(mode_frame, text="By Target Size", variable=self.upscale_mode, value="Size", command=self.toggle_upscale_mode).pack(side="left", padx=10)

        # Input for upscale value
        self.factor_entry = tk.Entry(self.upscale_tab)
        self.factor_entry.insert(0, "2")
        self.factor_entry.pack(pady=5)

        self.size_entry = tk.Entry(self.upscale_tab)
        self.size_entry.insert(0, "1920x1080")
        self.size_entry.pack(pady=5)
        self.size_entry.pack_forget()  # Hide initially

        # File list and preview
        self.thumbnail_frame_upscale = tk.Frame(self.upscale_tab, bg="white", height=250)
        self.thumbnail_frame_upscale.pack(fill="both", expand=True, padx=5, pady=5)

        self.upscale_canvas = tk.Canvas(self.thumbnail_frame_upscale, bg="white")
        self.upscale_scrollbar = ttk.Scrollbar(self.thumbnail_frame_upscale, orient="vertical", command=self.upscale_canvas.yview)
        self.upscale_scrollable_frame = tk.Frame(self.upscale_canvas, bg="white")
        self.upscale_scrollable_frame.bind("<Configure>", lambda e: self.upscale_canvas.configure(scrollregion=self.upscale_canvas.bbox("all")))

        self.upscale_canvas.create_window((0, 0), window=self.upscale_scrollable_frame, anchor="nw")
        self.upscale_canvas.configure(yscrollcommand=self.upscale_scrollbar.set)

        self.upscale_canvas.pack(side="left", fill="both", expand=True)
        self.upscale_scrollbar.pack(side="right", fill="y")

        # Enable drag and drop
        self.upscale_tab.drop_target_register(DND_FILES)
        self.upscale_tab.dnd_bind('<<Drop>>', self.handle_drop_upscale)

    def toggle_upscale_mode(self):
        if self.upscale_mode.get() == "Factor":
            self.factor_entry.pack(pady=5)
            self.size_entry.pack_forget()
        else:
            self.factor_entry.pack_forget()
            self.size_entry.pack(pady=5)

    def select_upscale_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Image Files", "*.jpg;*.png;*.jpeg")])
        if file_paths:
            self.upscale_files = file_paths  # Store selected files for upscaling
            self.update_upscale_thumbnails()  # Update thumbnails for upscaling

    def clear_upscale_selections(self):
        self.upscale_files.clear()  # Clear the upsize files list
        self.update_upscale_thumbnails()  # Clear the displayed thumbnails

    def update_upscale_thumbnails(self):
        # Remove existing thumbnails from the canvas
        for widget in self.upscale_scrollable_frame.winfo_children():
            widget.destroy()

        # Display new thumbnails for selected files
        for file in self.upscale_files:
            img = Image.open(file)
            img.thumbnail((100, 100))  # Resize the image for thumbnail
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(self.upscale_scrollable_frame, image=photo)
            label.image = photo  # Keep a reference to avoid garbage collection
            label.pack(side="left", padx=5, pady=5)

    def handle_drop_upscale(self, event):
        # Get the dropped file paths from the event
        dropped_files = event.data.splitlines()

        # Add files to the upsize_files list
        for file_path in dropped_files:
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
                self.upscale_files.append(file_path)
                # Create and show thumbnail in the upscale tab
                self.create_thumbnail_upscale(file_path)

    def create_thumbnail_upscale(self, file_path):
        # Create an image thumbnail for the dropped file
        try:
            # Open the image and create a thumbnail
            image = Image.open(file_path)
            image.thumbnail((100, 100))  # Resize to 100x100
            thumbnail = ImageTk.PhotoImage(image)

            # Create a new label with the thumbnail image
            thumbnail_label = tk.Label(self.upscale_scrollable_frame, image=thumbnail)
            thumbnail_label.image = thumbnail  # Keep reference to avoid garbage collection
            thumbnail_label.pack(side="left", padx=5, pady=5)

            # Add metadata (file size, dimensions) under the thumbnail
            metadata_label = tk.Label(self.upscale_scrollable_frame, text=f"{os.path.basename(file_path)}\n"
                                                                        f"Size: {image.size[0]}x{image.size[1]}\n"
                                                                        f"File: {self.get_file_size(file_path)}")
            metadata_label.pack(side="left", padx=5, pady=5)
        except Exception as e:
            print(f"Error creating thumbnail for {file_path}: {e}")

    def get_file_size(self, file_path):
        # Return the file size in a human-readable format (bytes, KB, MB)
        file_size = os.path.getsize(file_path)
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if file_size < 1024:
                return f"{file_size:.2f} {unit}"
            file_size /= 1024

    def start_upscale_thread(self):
        threading.Thread(target=self.upscale_images, daemon=True).start()

    def upscale_images(self):
        if not self.upscale_files:
            print("No files selected.")
            return

        upscale_by_factor = self.upscale_mode.get() == "Factor"

        # Determine thread count based on CPU usage
        max_threads = os.cpu_count() or 4
        current_load = psutil.cpu_percent(interval=1)
        thread_count = max(1, int(max_threads * (1 - current_load / 100)))

        print(f"Upscaling with {thread_count} threads (CPU load: {current_load}%)")

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = [executor.submit(self.process_image, file, upscale_by_factor) for file in self.upscale_files]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error: {e}")

        print("Upscaling complete.")

    def process_image(self, file_path, by_factor):
        try:
            img = Image.open(file_path)
            if by_factor:
                factor = float(self.factor_entry.get())
                new_size = (int(img.width * factor), int(img.height * factor))
            else:
                width, height = map(int, self.size_entry.get().lower().split("x"))
                new_size = (width, height)

            # Detect whether the image is art or photo (basic heuristic based on resolution)
            is_art = self.is_art_image(img)
            
            if is_art:
                img = self.upscale_with_waifu2x(img, new_size)
            else:
                img = self.upscale_with_opencv_dnn(img, new_size)

            base, ext = os.path.splitext(file_path)
            output_path = f"{base}_upscaled{ext}"
            img.save(output_path)

            print(f"Saved upscaled image to: {output_path}")
        except Exception as e:
            print(f"Failed to process {file_path}: {e}")

    def is_art_image(self, img):
        # Convert to grayscale
        gray = img.convert("L")
        
        # Edge detection
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_data = np.array(edges)
        edge_mean = np.mean(edge_data)

        # Color variance
        stat = ImageStat.Stat(img)
        color_variance = sum(stat.var) / len(stat.var)

        # Heuristic: High edges + low color variance → likely art
        if edge_mean > 20 and color_variance < 5000:
            return True
        return False

    def upscale_with_waifu2x(self, file_path):
        # Load the image
        img = Image.open(file_path)
        
        # Use Waifu2x for upscaling
        upscaled_image = waifu2x.upscale(img)

        # Save the upscaled image
        base, ext = os.path.splitext(file_path)
        output_path = f"{base}_upscaled{ext}"
        upscaled_image.save(output_path)

        print(f"Saved upscaled image to: {output_path}")

    def select_model_by_factor(self, factor):
        model_map = {
            2: 'EDSR_x2.pb',
            3: 'EDSR_x3.pb',
            4: 'EDSR_x4.pb'
        }
        
        return model_map.get(factor, 'EDSR_x3.pb')  # Default to EDSR_x3 if not found

    def upscale_with_opencv_dnn(self, img, factor):
        model_urls = {
            'EDSR_x2.pb': 'https://raw.githubusercontent.com/fannymonkey/EDSR/master/weights/EDSR_x2.pb',
            'EDSR_x3.pb': 'https://raw.githubusercontent.com/fannymonkey/EDSR/master/weights/EDSR_x3.pb',
            'EDSR_x4.pb': 'https://raw.githubusercontent.com/fannymonkey/EDSR/master/weights/EDSR_x4.pb',
        }
        model_name = self.select_model_by_factor(factor)
        model_path = download_model(model_urls[model_name], model_name)

        # Convert PIL Image to OpenCV format
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Prepare blob and set input
        blob = cv2.dnn.blobFromImage(img_cv, 1.0, (img_cv.shape[1], img_cv.shape[0]), (0, 0, 0), swapRB=False, crop=False)
        net = cv2.dnn.readNetFromTensorflow(model_path)
        net.setInput(blob)

        # Forward pass
        output = net.forward()

        # Post-process output
        output = output.squeeze().transpose((1, 2, 0))
        output = np.clip(output, 0, 255).astype(np.uint8)

        # Convert back to PIL Image
        upscaled_img = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB))
        return upscaled_img

#<-----------------Resize Tab helper functions---------------->

    def bind_arrow_keys(self):
        self.root.bind("<Left>", lambda event: self.adjust_slider_value(-1))
        self.root.bind("<Right>", lambda event: self.adjust_slider_value(1))

    def adjust_slider_value(self, delta):
        # Get the current value of the slider
        current_value = self.percentage_slider.get()
        # Adjust the value by delta (either +1 or -1)
        new_value = current_value + delta
        # Ensure the new value is within the allowed range
        new_value = max(1, min(300, new_value))  # Limit between 1 and 300 (or whatever range you set)
        # Set the new value and update the resized dimensions
        self.percentage_slider.set(new_value)
        self.update_resized_dimensions(str(new_value))  # Update resized dimensions based on new value

    def update_resized_dimensions(self, percent_str=None):
        try:
            if percent_str is None:
                percent = self.percentage_slider.get()  # If no argument, get from slider
            else:
                percent = int(percent_str)

            if not hasattr(self, 'original_width') or not hasattr(self, 'original_height'):
                print("Original dimensions not set.")
                return

            new_width = int(self.original_width * percent / 100)
            new_height = int(self.original_height * percent / 100)

            # Update the resized dimension label
            self.resized_size_label.config(
                text=f"Resized: {new_width} x {new_height}"
            )

        except Exception as e:
            print(f"Failed to calculate resized dimensions: {e}")

    def clear_resize_selections(self):
        # Clear the selected files list
        self.resize_files.clear()

        # Clear the thumbnail display
        for widget in self.thumbnail_frame_resize.winfo_children():
            widget.destroy()


        # Reset original/resized size labels
        self.original_size_label.config(text="Original: —")
        self.resized_size_label.config(text="Resized: —")

        # Clear width/height fields
        self.resize_width.delete(0, tk.END)
        self.resize_height.delete(0, tk.END)

        # Reset the slider to 100%
        self.percentage_slider.set(100)

        # Disable the slider again (optional)
        # self.percentage_slider.config(state="disabled")



    def toggle_resize_mode(self, mode):
        if mode == "Pixels":
            # Show width/height labels and entries
            self.resize_width_label.grid(row=2, column=0, sticky="e", padx=5, pady=5)
            self.resize_width.grid(row=2, column=1, padx=5, pady=5)

            self.resize_height_label.grid(row=3, column=0, sticky="e", padx=5, pady=5)
            self.resize_height.grid(row=3, column=1, padx=5, pady=5)

            # Hide percentage slider
            self.percentage_slider.grid_forget()
            self.keep_aspect_check.grid(row=4, column=0, columnspan=2, padx=5, pady=5)
            self.keep_aspect_check.configure(state="normal")
        elif mode == "Percentage":
            # Hide width/height labels and entries
            self.resize_width_label.grid_forget()
            self.resize_width.grid_forget()

            self.resize_height_label.grid_forget()
            self.resize_height.grid_forget()

            # Show percentage slider
            self.percentage_slider.configure(state="normal")
            self.percentage_slider.set(100)
            self.percentage_slider.grid(row=5, column=0, columnspan=2, padx=5, pady=5)
            self.keep_aspect.set(True)
            self.keep_aspect_check.grid_forget()  # hide the checkbox

    def select_resize_files(self):
        files = filedialog.askopenfilenames(title="Select Images", filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.heic")])

        if not files:
            return

        self.resize_files = list(files)
        self.display_resize_thumbnails(self.resize_files)

        # Load the first image to extract dimensions
        img = Image.open(self.resize_files[0])
        self.original_width, self.original_height = img.size  # Get original image dimensions

        # Update the original dimension label
        self.original_size_label.config(
            text=f"Original: {self.original_width} x {self.original_height}"
        )

        # Update the width and height text boxes with the original image size
        self.resize_width.delete(0, tk.END)
        self.resize_width.insert(0, str(self.original_width))

        self.resize_height.delete(0, tk.END)
        self.resize_height.insert(0, str(self.original_height))

        # Update resized dimensions initially based on percentage slider value
        self.update_resized_dimensions()


    def update_resize_fields_with_image(self):
        if not self.resize_files:
            return

        try:
            img = Image.open(self.resize_files[0])
            width, height = img.size
            self.resize_width.delete(0, tk.END)
            self.resize_width.insert(0, str(width))

            self.resize_height.delete(0, tk.END)
            self.resize_height.insert(0, str(height))
            self.original_size_label.config(text=f"Original: {width} x {height}")
        except Exception as e:
            print(f"Failed to get image size: {e}")


    def display_resize_thumbnails(self, files):
        if not files:
            return

        file = files[0]
        try:
            img = Image.open(file)
            img.thumbnail((300, 300))  # Resize for display
            self.thumbnail_image = ImageTk.PhotoImage(img)  # Keep a reference!

            if hasattr(self, 'thumbnail_label'):
                self.thumbnail_label.configure(image=self.thumbnail_image)
            else:
                self.thumbnail_label = tk.Label(self.thumbnail_frame_resize, image=self.thumbnail_image, bg="white")
                self.thumbnail_label.pack(padx=5, pady=5)

        except Exception as e:
            print(f"Failed to load thumbnail: {e}")

    def resize_images_threaded(self):
        if not self.resize_files:
            messagebox.showwarning("No Files", "Please select images to resize.")
            return

        output_dir = self.output_directory.get()
        if not output_dir:
            output_dir = os.path.join(os.path.dirname(self.resize_files[0]), "(resized)")
        os.makedirs(output_dir, exist_ok=True)

        resize_by_pct = self.resize_mode.get() == "Percentage"
        pct = self.percentage_slider.get()

        width = self.resize_width.get()
        height = self.resize_height.get()
        keep_aspect = self.keep_aspect.get()

        def parse_dim(value):
            try:
                return int(value) if value else None
            except ValueError:
                return None

        width = parse_dim(width)
        height = parse_dim(height)

        max_workers = max(1, os.cpu_count() - 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.resize_single_image, path, output_dir, resize_by_pct, pct, width, height, keep_aspect): path
                for path in self.resize_files
            }

            failed = []
            for future in as_completed(futures):
                file = futures[future]
                try:
                    result = future.result()
                    if not result:
                        failed.append(file)
                except Exception as e:
                    print(f"Exception while resizing {file}: {e}")
                    failed.append(file)

        if failed:
            messagebox.showwarning("Some Failures", f"{len(failed)} image(s) failed to resize.")
        else:
            messagebox.showinfo("Success", f"All images resized successfully to {output_dir}")

    def resize_single_image(self, path, output_dir, by_pct, pct, width, height, keep_aspect):
        try:
            img = Image.open(path)

            if by_pct:
                new_w = int(img.width * (pct / 100))
                new_h = int(img.height * (pct / 100))
            else:
                new_w = width or img.width
                new_h = height or img.height
                if keep_aspect and (width and not height):
                    new_h = int((new_w / img.width) * img.height)
                elif keep_aspect and (height and not width):
                    new_w = int((new_h / img.height) * img.width)

            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            output_path = os.path.join(output_dir, os.path.basename(path))
            resized.save(output_path)
            return True
        except Exception as e:
            print(f"Error resizing {path}: {e}")
            return False
        
    def handle_resize_dropped_files(self, event):
        dropped_files = self.root.tk.splitlist(event.data)
        print(f"Dropped files (resize): {dropped_files}")

        self.selected_resize_files = list(dropped_files)
        self.show_resize_thumbnails(self.selected_resize_files)

        # Load first image to get original dimensions
        try:
            with Image.open(self.selected_resize_files[0]) as img:
                width, height = img.size
                self.original_size_label.config(text=f"Original: {width}x{height}")
                self.update_resized_dimensions(str(self.percentage_slider.get()))
                self.resize_width.delete(0, tk.END)
                self.resize_width.insert(0, str(width))

                self.resize_height.delete(0, tk.END)
                self.resize_height.insert(0, str(height))
        except Exception as e:
            self.original_size_label.config(text="Original: —")
            self.resized_size_label.config(text="Resized: —")
            print(f"Error getting image size: {e}")


    def decrease_quality(self, event=None):
        # Check if the slider is currently visible
        if self.quality_label.winfo_ismapped() and self.quality_slider.winfo_ismapped():
            current_quality = self.quality.get()
            if current_quality > 1:  # Prevent going below 1
                self.quality.set(current_quality - 1)

    def increase_quality(self, event=None):
        # Check if the slider is currently visible
        if self.quality_label.winfo_ismapped() and self.quality_slider.winfo_ismapped():
            current_quality = self.quality.get()
            if current_quality < 100:  # Prevent going above 100
                self.quality.set(current_quality + 1)

    def toggle_quality_option(self, event=None):
        # Show or hide quality options based on format support
        format_key = self.output_format.get()
        if FORMAT_OPTIONS[format_key]['supports_quality']:
            self.quality_label.grid()
            self.quality_slider.grid()
        else:
            self.quality_label.grid_remove()
            self.quality_slider.grid_remove()

    def debounce_resize_event(self, event=None):
        # Only resize when width changes significantly; debounce resizing
        if hasattr(self, "_resize_job"):
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(500, self.adjust_canvas_and_thumbnails)

    def adjust_canvas_and_thumbnails(self):
        # Calculate columns based on canvas width and thumbnail size
        canvas_width = self.thumbnail_frame.winfo_width()
        new_columns = max(1, canvas_width // (self.thumbnail_size + 10))
        
        # Only update if column count changes
        if new_columns != self.columns:
            self.columns = new_columns
            print(f"Adjusted columns to: {self.columns}")
            self.update_thumbnail_preview_async()

    def handle_dropped_files(self, event):
        # Handle files dragged and dropped into the window
        dropped_files = self.root.tk.splitlist(event.data)
        print(f"Dropped files: {dropped_files}")  # Debug statement
        self.selected_files.extend(dropped_files)
        
        for file in dropped_files:
            ext = os.path.splitext(file)[1].lower()
            if ext.lower() in ['.nef', '.cr2', '.arw', '.dng']:
                print(f"Handling supported RAW file: {file}")  # Debug statement
            else:
                print(f"Unsupported file format dropped: {file}")  # Debug statement

        self.update_thumbnail_preview_async()

    def select_files(self):
        # Open file dialog for image selection
        filetypes = [("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.heic *.dng *.cr2 *.arw *.nef"), ("All files", "*.*")]
        selected = filedialog.askopenfilenames(title="Select Images", filetypes=filetypes)
        self.selected_files.extend(selected)
        print(f"Selected files: {selected}")
        self.update_thumbnail_preview_async()

    def clear_selections(self):
        # Clear selected files and thumbnails
        self.selected_files.clear()
        self.thumbnails.clear()
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        print("Selections cleared.")

    def select_output_directory(self):
        # Open directory dialog for output folder
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_directory.set(directory)
            self.output_dir_display.config(text=directory)
            print(f"Output directory set to: {directory}")

    def update_thumbnail_preview_async(self):
        # Ensure that only one thread is loading thumbnails at any time
        if self.loading_thread is None or not self.loading_thread.is_alive():
            print("Starting thumbnail loading thread")
            self.loading_thread = threading.Thread(target=self.update_thumbnail_preview, daemon=True)
            self.loading_thread.start()

    def update_thumbnail_preview(self):
        """Load and display thumbnails for all selected files with a persistent removable 'X' button."""
        with self.lock:
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()

            unique_files = list(dict.fromkeys(self.selected_files))  # Remove duplicate files
            self.thumbnails.clear()  # Prevent garbage collection issues

            for index, file_path in enumerate(unique_files):
                try:
                    # For .arw files, generate a thumbnail from the raw data
                    if file_path.lower().endswith('.arw'):
                        img = generate_thumbnail(file_path)  # Use the rawpy-based thumbnail generator
                    else:
                        img = Image.open(file_path)  # For other file types, use PIL

                    # Create the initial thumbnail with the "X" button only
                    overlay_thumbnail = self.create_thumbnail_with_x(img)

                    self.thumbnails.append(overlay_thumbnail)

                    row, col = divmod(index, self.columns)
                    label = tk.Label(self.scrollable_frame, image=overlay_thumbnail, bg="white")
                    label.grid(row=row, column=col, padx=5, pady=5)

                    # Bind click event to check if "X" button was clicked
                    label.bind("<Button-1>", lambda e, path=file_path: self.remove_selection(path) if self.clicked_x(e) else None)
                    self.thumbnail_labels[file_path] = {"label": label, "image": overlay_thumbnail}
                except Exception as e:
                    print(f"Failed to load image {file_path}: {e}")
                    continue

    def create_thumbnail_with_x(self, img):
        """Create a thumbnail with an enlarged canvas and 'X' button overlay."""
        canvas_size = (self.thumbnail_size + 20, self.thumbnail_size + 20)
        offset = 10

        canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
        img.thumbnail((self.thumbnail_size, self.thumbnail_size))
        canvas.paste(img, (offset, offset))

        # Draw "X" on canvas
        draw = ImageDraw.Draw(canvas)
        self.draw_remove_icon(draw, canvas.width, canvas.height)

        return ImageTk.PhotoImage(canvas)

    def clicked_x(self, event):
        """Detect if the click is on the 'X' button region of the thumbnail."""
        # Coordinates and size of the "X" button
        x_button_x, x_button_y, radius = 15, 15, 10  # Adjust to the position of the "X" button
        x_button_bounds = (
            x_button_x - radius, x_button_y - radius,
            x_button_x + radius, x_button_y + radius
        )
        # Check if click falls within "X" button area
        return x_button_bounds[0] <= event.x <= x_button_bounds[2] and x_button_bounds[1] <= event.y <= x_button_bounds[3]

    def overlay_check_mark(self, file_path):
        """Add a checkmark to an existing thumbnail while preserving the 'X' button, adapting for different aspect ratios."""
        thumbnail_info = self.thumbnail_labels.get(file_path)
        if thumbnail_info:
            # Load and resize the image for the thumbnail
            img = Image.open(file_path)
            img.thumbnail((self.thumbnail_size, self.thumbnail_size))

            # Set up the canvas and paste the thumbnail at an offset
            canvas_size = (self.thumbnail_size + 20, self.thumbnail_size + 20)
            offset = 10
            canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
            canvas.paste(img, (offset, offset))

            # Draw the "X" button on the canvas
            draw = ImageDraw.Draw(canvas)
            self.draw_remove_icon(draw, canvas.width, canvas.height)

            # Calculate the checkmark position based on actual thumbnail size within the canvas
            actual_width, actual_height = img.size
            checkmark_offset_x = offset + actual_width - 15
            checkmark_offset_y = offset + actual_height - 15
            circle_radius = 10

            # Draw the green checkmark circle
            draw.ellipse(
                [
                    (checkmark_offset_x - circle_radius, checkmark_offset_y - circle_radius),
                    (checkmark_offset_x + circle_radius, checkmark_offset_y + circle_radius)
                ],
                fill="green"
            )

            # Draw the checkmark symbol inside the circle
            checkmark_color = "white"
            draw.line([(checkmark_offset_x - 4, checkmark_offset_y), 
                    (checkmark_offset_x, checkmark_offset_y + 4), 
                    (checkmark_offset_x + 6, checkmark_offset_y - 6)], fill=checkmark_color, width=2)

            # Update the label's image with the modified thumbnail
            updated_thumbnail = ImageTk.PhotoImage(canvas)
            thumbnail_info["label"].configure(image=updated_thumbnail)
            thumbnail_info["label"].image = updated_thumbnail  # Keep reference to prevent garbage collection
            print(f"Checkmark and 'X' applied to {file_path}")

    def draw_remove_icon(self, draw, img_width, img_height):
        """Draw the 'X' button in the top-left corner."""
        circle_radius = 10
        circle_center = (15, 15)  # Position slightly within bounds for visibility

        # Draw circle background for "X"
        draw.ellipse(
            [
                (circle_center[0] - circle_radius, circle_center[1] - circle_radius),
                (circle_center[0] + circle_radius, circle_center[1] + circle_radius)
            ],
            fill="red"
        )

        # Draw "X" within the circle
        x_color = "white"
        x_offset = 4  # Define "X" size within the circle
        x_start = (circle_center[0] - x_offset, circle_center[1] - x_offset)
        x_end = (circle_center[0] + x_offset, circle_center[1] + x_offset)
        draw.line([x_start, x_end], fill=x_color, width=2)
        draw.line([(x_start[0], x_end[1]), (x_end[0], x_start[1])], fill=x_color, width=2)


    def handle_thumbnail_click(self, event, file_path, img):
        """Handle click on the thumbnail to remove it if 'X' is clicked, or enlarge if elsewhere."""
        # Coordinates of the "X" button bounding box
        x_button_x, x_button_y, radius = 15, 15, 10  # Position and size of the "X" button
        x_button_bounds = (
            x_button_x - radius, x_button_y - radius,
            x_button_x + radius, x_button_y + radius
        )

        # Check if click is within the bounds of the "X" button
        if x_button_bounds[0] <= event.x <= x_button_bounds[2] and x_button_bounds[1] <= event.y <= x_button_bounds[3]:
            self.remove_selection(file_path)  # Click on "X" button removes the thumbnail

    def add_remove_icon(self, img, file_path):
        """Create a larger canvas with a floating circular 'X' button positioned close to the image corner."""
        # Define the expanded canvas size, slightly larger than the thumbnail
        canvas_size = (self.thumbnail_size + 20, self.thumbnail_size + 20)
        offset = 10  # Offset to center the image within the larger canvas

        # Create a blank canvas with a transparent background
        canvas = Image.new("RGBA", canvas_size, (255, 255, 255, 0))
        canvas.paste(img, (offset, offset))  # Center the image on the canvas

        # Draw the "X" button near the top-left corner of the image, within the expanded canvas
        draw = ImageDraw.Draw(canvas)
        circle_radius = 10
        # Position circle to be partially off the top-left but fully within the expanded canvas
        circle_center = (offset + 5, offset + 5)  # Position slightly inwards to avoid canvas edges

        # Draw circle background
        draw.ellipse(
            [
                (circle_center[0] - circle_radius, circle_center[1] - circle_radius),
                (circle_center[0] + circle_radius, circle_center[1] + circle_radius)
            ],
            fill="red"
        )

        # Draw the "X" inside the circle
        x_color = "white"
        x_offset = 4  # Adjust for a smaller "X" to fit nicely inside the circle
        x_start = (circle_center[0] - x_offset, circle_center[1] - x_offset)
        x_end = (circle_center[0] + x_offset, circle_center[1] + x_offset)
        draw.line([x_start, x_end], fill=x_color, width=2)
        draw.line([(x_start[0], x_end[1]), (x_end[0], x_start[1])], fill=x_color, width=2)

        # Return the updated image as a Tkinter-compatible image
        return ImageTk.PhotoImage(canvas)

    def remove_selection(self, file_path):
        """Remove a file from the selected files list and update the display."""
        if file_path in self.selected_files:
            self.selected_files.remove(file_path)
            self.update_thumbnail_preview_async()

    def convert_single_image(self, file_path, output_dir, output_ext, quality):
        """Convert a single image and save it to the output directory, then add a checkmark if successful."""
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}.{output_ext}")

        try:
            # Open image
            RAW_EXTENSIONS = ['.nef', '.cr2', '.arw', '.dng']
            if any(file_path.lower().endswith(ext) for ext in RAW_EXTENSIONS):
                with rawpy.imread(file_path) as raw:
                    rgb_array = raw.postprocess()
                image = Image.fromarray(rgb_array)
            else:
                image = Image.open(file_path)

            # Save image in specified format
            save_options = {'quality': quality} if quality else {}
            image.save(output_path, format=output_ext.upper(), **save_options)
            
            print(f"Converted {file_path} to {output_path}")
            
            # Apply checkmark overlay to the thumbnail
            self.overlay_check_mark(file_path)
            return True

        except Exception as e:
            print(f"Failed to convert {file_path}: {e}")
            return False

    def convert_images(self):
        if not self.selected_files:
            messagebox.showwarning("Warning", "Please select images to convert.")
            return
        
        failed_files = []

        # Prepare output directory
        output_dir = self.output_directory.get()
        if not output_dir:
            output_dir = os.path.join(os.path.dirname(self.selected_files[0]), "(directory-converted)")
        os.makedirs(output_dir, exist_ok=True)

        # Output format and settings
        format_key = self.output_format.get()
        output_ext = FORMAT_OPTIONS[format_key]['ext']
        quality = self.quality.get() if FORMAT_OPTIONS[format_key]['supports_quality'] else None

        # Set up the thread pool
        max_workers = max(1, os.cpu_count() - 1)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.convert_single_image, file_path, output_dir, output_ext, quality): file_path
                for file_path in self.selected_files
            }

            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    success = future.result()
                    if not success:
                        failed_files.append((file_path, "Unknown error"))
                        print(f"Failed to convert: {file_path}")
                    else:
                        print(f"Successfully converted: {file_path}")
                except Exception as e:
                    failed_files.append((file_path, str(e)))
                    print(f"Exception for {file_path}: {e}")

        if failed_files:
            error_message = "\n\n".join(
                f"{os.path.basename(path)}:\n{err}" for path, err in failed_files[:5]
            )
            if len(failed_files) > 5:
                error_message += f"\n\n...and {len(failed_files) - 5} more failures."
            messagebox.showerror("Conversion Errors", f"Some files failed to convert:\n\n{error_message}")
        else:
            messagebox.showinfo("Success", f"All images converted successfully to:\n{output_dir}")

    def convert_images_threaded(self):
        conversion_thread = threading.Thread(target=self.convert_images)
        conversion_thread.start()

def generate_thumbnail(file_path, size=(128, 128)):
    """Generate a high-quality thumbnail from a raw image file."""
    try:
        with rawpy.imread(file_path) as raw:
            # Post-process the raw image into RGB
            rgb_array = raw.postprocess()
            # Resize the result to create a thumbnail
            thumbnail_img = Image.fromarray(rgb_array).resize(size, Image.Resampling.LANCZOS)
            return thumbnail_img
    except Exception as e:
        print(f"Failed to generate thumbnail for {file_path}: {e}")
        return None


if __name__ == "__main__":
    root = TkinterDnD.Tk()  # Use TkinterDnD for drag-and-drop
    app = ImageConverterApp(root)
    root.mainloop()
