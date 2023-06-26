# Convert a SAM model checkpoint to a ggml compatible file
#

import os
import sys
import code
import json
import torch
import struct
import numpy as np

if len(sys.argv) < 3:
    print("Usage: convert-pth-to-ggml.py file-model ftype\n")
    print("  ftype == 0 -> float32")
    print("  ftype == 1 -> float16")
    sys.exit(1)

# output in the same directory as the model
fname_model = sys.argv[1]
fname_out   = os.path.dirname(fname_model) + "/ggml-model.bin"

# possible data types
#   ftype == 0 -> float32
#   ftype == 1 -> float16
#
# map from ftype to string
ftype_str = ["f32", "f16"]

ftype = 1
if len(sys.argv) > 2:
    ftype = int(sys.argv[2])

if ftype < 0 or ftype > 1:
    print("Invalid ftype: " + str(ftype))
    sys.exit(1)

fname_out = fname_out.replace(".bin", "-" + ftype_str[ftype] + ".bin")

model = torch.load(fname_model, map_location="cpu")

# TODO: determine based on model data
# TODO: add decoder / prompt encoder if needed
hparams = {
    "n_enc_state":      768,
    "n_enc_layers":      12,
    "n_enc_heads":       12,
    "n_enc_out_chans":  256,

    "n_pt_embd": 4,
}

print(hparams)

for k, v in model.items():
    print(k, v.shape)

#exit()
#code.interact(local=locals())

fout = open(fname_out, "wb")

fout.write(struct.pack("i", 0x67676d6c)) # magic: ggml in hex
fout.write(struct.pack("i", hparams["n_enc_state"]))
fout.write(struct.pack("i", hparams["n_enc_layers"]))
fout.write(struct.pack("i", hparams["n_enc_heads"]))
fout.write(struct.pack("i", hparams["n_enc_out_chans"]))
fout.write(struct.pack("i", hparams["n_pt_embd"]))
fout.write(struct.pack("i", ftype))

for k, v in model.items():
    name = k
    shape = v.shape

    # TODO: export only the Encoder -- after it works we will export the other stuff
    if name[:13] != "image_encoder" and \
       name[:14] != "prompt_encoder":
        continue

    if name[:19] == "prompt_encoder.mask":
        continue

    print("Processing variable: " + name + " with shape: ", shape, " and type: ", v.dtype)

    #data = tf.train.load_variable(dir_model, name).squeeze()
    #data = v.numpy().squeeze()
    data = v.numpy()
    n_dims = len(data.shape);

    # for efficiency - transpose some matrices
    # "model/h.*/attn/c_attn/w"
    # "model/h.*/attn/c_proj/w"
    # "model/h.*/mlp/c_fc/w"
    # "model/h.*/mlp/c_proj/w"
    #if name[-14:] == "/attn/c_attn/w" or \
    #   name[-14:] == "/attn/c_proj/w" or \
    #   name[-11:] == "/mlp/c_fc/w" or \
    #   name[-13:] == "/mlp/c_proj/w":
    #    print("  Transposing")
    #    data = data.transpose()

    dshape = data.shape

    # default type is fp16
    ftype_cur = 1
    if ftype == 0 or n_dims == 1 or \
            name == "image_encoder.pos_embed" or \
            name.startswith("prompt_encoder.point_embeddings"):
        print("  Converting to float32")
        data = data.astype(np.float32)
        ftype_cur = 0
    else:
        print("  Converting to float16")
        data = data.astype(np.float16)

    # reshape the 1D bias into a 4D tensor so we can use ggml_repeat
    # keep it in F32 since the data is small
    if name == "image_encoder.patch_embed.proj.bias":
        data = data.reshape(1, data.shape[0], 1, 1)
        n_dims = len(data.shape);
        dshape = data.shape

    print("  New shape: ", dshape)

    # header
    str = name.encode('utf-8')
    fout.write(struct.pack("iii", n_dims, len(str), ftype_cur))
    for i in range(n_dims):
        fout.write(struct.pack("i", dshape[n_dims - 1 - i]))
    fout.write(str);

    # data
    data.tofile(fout)

fout.close()

print("Done. Output file: " + fname_out)
print("")
