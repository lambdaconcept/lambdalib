"""Host-side software for ILA"""
from argparse import ArgumentParser
from serial import Serial
from vcd import VCDWriter


def parse_layout(layout_str):
    """Parse signal layout string into list of (name, width) tuples.
    
    Args:
        layout_str: String like 'data_in:10,trigger:1,address:8'
        
    Returns:
        List of (signal_name, width) tuples
        
    Raises:
        ValueError: If layout string is malformed
    """
    signals = []
    if not layout_str.strip():
        raise ValueError("Layout string cannot be empty")
        
    for signal_def in layout_str.split(','):
        signal_def = signal_def.strip()
        if ':' not in signal_def:
            raise ValueError(f"Invalid signal definition '{signal_def}'. Expected format 'name:width'")
            
        name, width_str = signal_def.split(':', 1)
        name = name.strip()
        width_str = width_str.strip()
        
        if not name:
            raise ValueError(f"Signal name cannot be empty in '{signal_def}'")
            
        try:
            width = int(width_str)
            if width <= 0:
                raise ValueError(f"Signal width must be positive, got {width} for '{name}'")
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"Invalid width '{width_str}' for signal '{name}'. Width must be a positive integer")
            raise
            
        signals.append((name, width))
    
    return signals


def extract_signal_value(data_value, bit_offset, width):
    """Extract a signal value from the packed data.
    
    Args:
        data_value: Full packed data value
        bit_offset: Starting bit position (LSB = 0)
        width: Number of bits to extract
        
    Returns:
        Extracted signal value
    """
    mask = (1 << width) - 1
    return (data_value >> bit_offset) & mask


if __name__ == "__main__":
    parser = ArgumentParser(description="ILA Capture Tool")
    parser.add_argument("port", help="Serial port for ILA data")
    parser.add_argument("output", help="Output VCD file")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate for serial communication (default: 115200)")
    parser.add_argument("--depth", type=int, required=True, help="Number of samples captured by ILA")
    parser.add_argument("--layout", type=str, required=True, help="Signal layout description (e.g. 'data_in:10,trigger:1,address:8')")
    args = parser.parse_args()

    # Parse and validate the layout
    try:
        signals = parse_layout(args.layout)
    except ValueError as e:
        print(f"Error parsing layout: {e}")
        exit(1)
    
    # Calculate data width from layout
    data_width = sum(width for _, width in signals)
    
    print(f"Parsed layout: {signals}")
    print(f"Inferred data width: {data_width} bits")
    print(f"Waiting for {args.depth} samples of {data_width}-bit data from {args.port}")

    try:
        with Serial(args.port, args.baudrate, timeout=None) as ser, open(args.output, "w") as vcd_file:
            with VCDWriter(vcd_file, timescale="1 ns") as vcd:
                # Register clock signal
                clk_signal = vcd.register_var("ila", "clk", "wire", size=1)
                
                # Register all signals in the VCD
                vcd_signals = []
                for name, width in signals:
                    vcd_signal = vcd.register_var("ila", name, "wire", size=width)
                    vcd_signals.append(vcd_signal)
                
                # Initialize clock signal to low
                vcd.change(clk_signal, 0, 0)
                
                # Capture and decode samples
                bytes_to_read = (data_width + 7) // 8  # Round up to nearest byte
                print(f"Waiting for data on {args.port}... (Press Ctrl+C to abort)")
                
                for sample_index in range(args.depth):
                    # Read raw data from serial port - this will block until data is available
                    raw_data = ser.read(bytes_to_read)
                    
                    if len(raw_data) < bytes_to_read:
                        print(f"Incomplete data received at sample {sample_index}. Expected {bytes_to_read} bytes, got {len(raw_data)}. Exiting.")
                        break
                    
                    # Convert bytes to integer (little-endian)
                    data_value = int.from_bytes(raw_data, byteorder='little')
                    
                    # Extract and log individual signal values
                    bit_offset = 0
                    timestamp = sample_index * 1000  # 1ns timestep, 1us per sample
                    
                    # Generate clock signal - rising edge at start of each sample
                    vcd.change(clk_signal, timestamp, 1)
                    
                    for (name, width), vcd_signal in zip(signals, vcd_signals):
                        signal_value = extract_signal_value(data_value, bit_offset, width)
                        vcd.change(vcd_signal, timestamp, signal_value)
                        bit_offset += width

                    # Falling edge at middle of sample period
                    vcd.change(clk_signal, timestamp + 500, 0)
                        
                    if sample_index % 100 == 0:  # Progress indicator
                        print(f"Processed {sample_index + 1}/{args.depth} samples")
                        
        print(f"Data capture complete. Output written to {args.output}")
        
    except KeyboardInterrupt:
        print(f"\nCapture interrupted by user. Partial data written to {args.output}")
    except Exception as e:
        print(f"Error during capture: {e}")
        exit(1)
