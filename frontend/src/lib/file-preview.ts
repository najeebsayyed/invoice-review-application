export function createFilePreview(file: Blob) {
  const reader = new FileReader()
  const result = new Promise<string>((resolve, reject) => {
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result)
        return
      }
      reject(new Error('The selected file could not be prepared for preview.'))
    }
    reader.onerror = () => reject(reader.error ?? new Error('The selected file could not be read.'))
    reader.onabort = () => reject(new DOMException('Preview read was cancelled.', 'AbortError'))
    reader.readAsDataURL(file)
  })

  return {
    result,
    abort: () => reader.abort(),
  }
}
