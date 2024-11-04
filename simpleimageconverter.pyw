#V1.7 04/11/24
#Added ability to remove individual images by clicking the "x"

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
        """Load and display thumbnails for all selected files with a persistent removable 'X' button."""
        with self.lock:
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            
            unique_files = list(dict.fromkeys(self.selected_files))  # Remove duplicate files
            self.thumbnails.clear()  # Prevent garbage collection issues

            for index, file_path in enumerate(unique_files):
                try:
                    img = Image.open(file_path)
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
            RAW_EXTENSIONS = ['.nef', '.cr2', '.arw']
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
