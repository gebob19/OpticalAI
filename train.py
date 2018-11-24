import threading
import optparse

import cv2
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from keras.losses import mean_squared_error
from keras.optimizers import RMSprop
from keras.callbacks import ReduceLROnPlateau, ModelCheckpoint, EarlyStopping, TensorBoard

from model import mobnet

class ThreadSafeIterator:
    def __init__(self, it):
        self.it = it
        self.lock = threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self.lock:
            return self.it.__next__()

def threadsafe_generator(f):
    """
    A decorator that takes a generator function and makes it thread-safe.
    """
    def g(*args, **kwargs):
        return ThreadSafeIterator(f(*args, **kwargs))

    return g

@threadsafe_generator
def train_generator(df, shape):
    while True:
        shuffle_indices = np.arange(len(df))
        shuffle_indices = np.random.permutation(shuffle_indices)
        
        for start in range(0, len(df), BATCH_SIZE):
            end = min(start + BATCH_SIZE, len(df))
            df_batch = df.iloc[shuffle_indices[start:end]]
            
            x_batch = []
            y_batch = []
            
            xcam = df_batch['XCam']
            ycam = df_batch['YCam']
            
            for index, _fn in enumerate(df_batch['file_names']):
                img = cv2.imread('{}/{}'.format(dset_path, _fn))
                img = cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)

#               # === You can add data augmentations here. === #
#                 if np.random.random() < 0.5:
#                     img, mask = img[:, ::-1, :], mask[..., ::-1, :]  # random horizontal flip
                
                y_batch.append(xcam[index], ycam[index])
                x_batch.append(img)
            
            yield np.asarray(x_batch), np.asarray(y_batch)

if __name__ == '__main__':
    dset_path = '../gazecapture'

    parser = optparse.OptionParser()

    parser.add_option('-e', '--epochs',
    action="store", dest="epochs",
    help="epochs", default="10")

    parser.add_option('-b', '--batch_size',
    action="store", dest="bs",
    help="b", default="16")

    parser.add_option('-s', '--shape',
    action="store", dest="s",
    help="s", default="(224, 224, 3)")

    parser.add_option('-l', '--lr',
    action="store", dest="lr",
    help="lr", default="1e-3")

    options, args = parser.parse_args()

    epochs = int(options.epochs)
    BATCH_SIZE = int(options.bs)
    shape = eval(options.s)
    resize = eval(options.r)

    # learning_rate = [4e-3, 1e-3]
    # # 224, 224, 3 with pretrained weigths ~ 7 epochs => train mae ~2cm
    # shapes = (320, 568, 3)
    # model_resize = (450, 512, 1)
    # model_weights = [None, None, None]
    

    # testdf = pd.read_csv('test-df.csv')
    train = pd.read_csv('portrait-train-df.csv')
    val = pd.read_csv('portrait-train-df.csv')

    # train, val = train_test_split(traindf, test_size=0.1)

    model_name = "basemodel_{}".format(shape)
    model = mobnet(shape, 'imagenet')

    model.compile(loss = {'y_xcam': mean_squared_error,
                        'y_ycam': mean_squared_error},
            optimizer = RMSprop(1e-3),
                metrics = ['mae'])

    callbacks = [
        ReduceLROnPlateau(monitor='val_loss',
                        factor=0.2,
                        patience=4,
                        verbose=1,
                        min_delta=1e-5),
        TensorBoard(log_dir='./logs/{}-logs'.format(model_name),
                    batch_size=BATCH_SIZE)
    ]

    model.fit_generator(generator=train_generator(train, shape),
                            steps_per_epoch=np.ceil(float(len(train)) / float(BATCH_SIZE)),
                            epochs=epochs,
                            verbose=1,
                            callbacks=callbacks,
                            validation_data=train_generator(val, shape),
                            validation_steps=np.ceil(float(len(val)) / float(BATCH_SIZE)))
