from freetype import *
face = Face("/Library/TeX/Root/texmf-dist/fonts/type1/public/mlmodern/mlmtt10.pfb")
print('Glyphs:', face.num_glyphs)
#for c in face.get_chars():
#   print(c)
face.set_char_size(48*64*4)
face.load_char('S')
bitmap = face.glyph.bitmap
print('Width:', bitmap.width)

from PIL import Image
image = Image.frombytes("L", (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
#image = image.convert("1")
image.save("letter.png")

# This convert it to JPEG-XL: 
#   cjxl -q 100 letter.png letter.jxl
