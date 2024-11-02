#V1.6 02/11/24
#Made checkmark more visible
#Fixed some import statements
import subprocess
import sys

# Function to check and install missing dependencies
def check_and_install(package):
    try:
        __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])

def install_dependencies():
    packages = ['Pillow', 'pillow-heif', 'tkinterdnd2', 'pillow-avif-plugin', 'rawpy']
    for package in packages:
        check_and_install(package)

install_dependencies()

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import TkinterDnD, DND_FILES  # Drag-and-drop support
from PIL import Image, ImageDraw, ImageTk, ImageFont
from pillow_heif import register_heif_opener
import rawpy
from concurrent.futures import ThreadPoolExecutor, as_completed

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

class ImageConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Image Converter")

        # Set fixed size limits for the window to prevent unintended expansion
        self.root.minsize(600, 600)
        self.root.maxsize(1000, 800)
        
        # Initialize variables
        self.selected_files = []
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
        # File selection buttons
        tk.Button(self.root, text="Select Images", command=self.select_files).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(self.root, text="Clear Selections", command=self.clear_selections).grid(row=0, column=1, padx=5, pady=5)

        # Output format selection
        tk.Label(self.root, text="Output Format").grid(row=1, column=0, padx=5, pady=5)
        format_menu = ttk.Combobox(self.root, textvariable=self.output_format, values=list(FORMAT_OPTIONS.keys()), state="readonly")
        format_menu.grid(row=1, column=1, padx=5, pady=5)
        format_menu.bind("<<ComboboxSelected>>", self.toggle_quality_option)

        # Quality setting for JPEG as a slider
        self.quality_label = tk.Label(self.root, text="Quality (1-100):")
        self.quality_label.grid(row=2, column=0, padx=5, pady=5)

        self.quality_slider = tk.Scale(self.root, variable=self.quality, from_=1, to=100, orient=tk.HORIZONTAL)
        self.quality_slider.grid(row=2, column=1, padx=5, pady=5)
        self.toggle_quality_option()

        # Bind arrow keys to control the slider on the main window
        self.root.bind("<Left>", self.decrease_quality)
        self.root.bind("<Right>", self.increase_quality)

        # Output directory selection
        tk.Button(self.root, text="Select Output Directory", command=self.select_output_directory).grid(row=3, column=0, padx=5, pady=5)
        self.output_dir_display = tk.Label(self.root, text="No output directory selected. (Will create default)")
        self.output_dir_display.grid(row=3, column=1, padx=5, pady=5)

        # Image thumbnail preview area
        self.thumbnail_frame = tk.Frame(self.root, bg="white")
        self.thumbnail_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=10, sticky='nsew')

        # Make the row and column expandable
        self.root.grid_rowconfigure(4, weight=1)  # Make row 4 expandable
        self.root.grid_columnconfigure(0, weight=1)  # Make column 0 expandable
        self.root.grid_columnconfigure(1, weight=1)  # Make column 1 expandable

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
        tk.Button(self.root, text="Convert Images", command=self.convert_images_threaded).grid(row=5, column=0, columnspan=2, pady=10)

        # Track window resizing to dynamically adjust thumbnail size and canvas width
        self.root.bind("<Configure>", self.debounce_resize_event)

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
        filetypes = [("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff *.heic"), ("All files", "*.*")]
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
        """Load and display thumbnails for all selected files in a grid layout."""
        with self.lock:
            # Clear existing thumbnails only once
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            unique_files = list(dict.fromkeys(self.selected_files))  # Remove duplicate files
            self.thumbnails.clear()  # Clear old references to prevent garbage collection

            # Load and display thumbnails in a grid layout
            for index, file_path in enumerate(unique_files):
                try:
                    print(f"Loading thumbnail for: {file_path}")
                    img = Image.open(file_path)
                    img.thumbnail((self.thumbnail_size, self.thumbnail_size))
                    thumbnail = ImageTk.PhotoImage(img)
                    self.thumbnails.append(thumbnail)  # Prevent garbage collection

                    # Place thumbnails in a grid layout
                    row = index // self.columns
                    col = index % self.columns
                    label = tk.Label(self.scrollable_frame, image=thumbnail, bg="white")
                    label.grid(row=row, column=col, padx=5, pady=5)

                    # Store both the label and original image for overlaying check mark later
                    self.thumbnail_labels[file_path] = {"label": label, "image": img}
                except Exception as e:
                    print(f"Failed to load image {file_path}: {e}")
                    continue

            print(f"Total thumbnails loaded: {len(self.thumbnails)}")

    def overlay_check_mark(self, file_path):
        """Overlay a transparent circle with a green outline and a white check mark inside it."""
        thumbnail_info = self.thumbnail_labels.get(file_path)
        if thumbnail_info:
            img = thumbnail_info["image"]
            draw = ImageDraw.Draw(img)

            img_width, img_height = img.size

            # Define properties
            check_mark = "✔"
            circle_radius = 10  # Radius for the surrounding circle
            font_size = 30  # Size for the check mark

            # Load a custom font if available (Arial in this example)
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()  # Fallback to default font if custom font is unavailable

            # Position: bottom-right, accounting for circle radius
            text_position = (img_width - circle_radius * 2-10, img_height - circle_radius * 2-12)
            circle_position = (img_width - 30 , img_height - 30 ,
                           img_width - 5,img_height - 5)

            # Draw a transparent circle with a green outline
            draw.ellipse(circle_position, fill="green", outline="green", width=3)

            # Draw the check mark inside the circle
            draw.text(text_position, check_mark, fill=None, font=font)

            # Update the label's image with the modified thumbnail
            updated_thumbnail = ImageTk.PhotoImage(img)
            thumbnail_info["label"].configure(image=updated_thumbnail)
            thumbnail_info["label"].image = updated_thumbnail  # Prevent garbage collection

            print(f"Check mark applied to {file_path}")


    def convert_single_image(self, file_path, output_dir, output_ext, quality):
        """Convert a single image and save it to the output directory."""
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(output_dir, f"{base_name}.{output_ext}")

        try:
            # Determine if the file is a RAW format supported by rawpy
            RAW_EXTENSIONS = ['.nef', '.cr2', '.arw']
            if any(file_path.lower().endswith(ext) for ext in RAW_EXTENSIONS):
                print(f"Using rawpy to open {file_path}")
                with rawpy.imread(file_path) as raw:
                    rgb_array = raw.postprocess()
                image = Image.fromarray(rgb_array)
            else:
                # Open non-RAW files with Pillow
                print(f"Using Pillow to open {file_path}")
                image = Image.open(file_path)

            # Save the image in the specified output format
            if output_ext.lower() == "jxl":
                self.save_as_jxl(image, output_path, quality=quality or 100)
            else:
                save_options = {'quality': quality} if quality else {}
                image.save(output_path, format=output_ext.upper(), **save_options)
            
            print(f"Converted {file_path} to {output_path}")
            self.overlay_check_mark(file_path)
            return True

        except Exception as e:
            print(f"Failed to convert {file_path}: {e}")
            return False

    def convert_images(self):
        if not self.selected_files:
            messagebox.showwarning("Warning", "Please select images to convert.")
            return

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
            # Submit tasks to the executor
            futures = {executor.submit(self.convert_single_image, file_path, output_dir, output_ext, quality): file_path for file_path in self.selected_files}
            
            # Process results as each conversion completes
            for future in as_completed(futures):
                file_path = futures[future]
                try:
                    success = future.result()
                    if success:
                        print(f"Successfully converted: {file_path}")
                    else:
                        print(f"Failed to convert: {file_path}")
                except Exception as e:
                    print(f"Exception for {file_path}: {e}")

        print(f"Images successfully converted to {output_dir}")
        messagebox.showinfo("Success", f"Images converted successfully to {output_dir}")

    def convert_images_threaded(self):
        conversion_thread = threading.Thread(target=self.convert_images)
        conversion_thread.start()

if __name__ == "__main__":
    root = TkinterDnD.Tk()  # Use TkinterDnD for drag-and-drop
    app = ImageConverterApp(root)
    root.mainloop()
