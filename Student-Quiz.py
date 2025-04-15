def stream_hello_world():
    while True:
        yield "Hello World\n"
        time.sleep(1)

# Example usage:
for message in stream_hello_world():
    print(message, end='', flush=True)
