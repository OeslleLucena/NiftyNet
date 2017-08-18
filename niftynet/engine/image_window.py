# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import tensorflow as tf

N_SPATIAL = 3
LOCATION_FORMAT = "{}_location"
BUFFER_POSITION_DTYPE = tf.int32


# TF_NP_DTYPES = {tf.int32: np.int32, tf.float32: np.float32}


class ImageWindow(object):
    def __init__(self, names, shapes, dtypes):
        self.names = names
        self.shapes = shapes
        self.dtypes = dtypes
        self.n_samples = 1
        self.has_dynamic_shapes = self._check_dynamic_shapes()
        self._placeholders_dict = None

    @classmethod
    def from_data_reader_properties(cls,
                                    source_names,
                                    image_shapes,
                                    image_dtypes,
                                    data_param):
        input_names = tuple(source_names)
        # complete window shapes based on user input and input_image sizes
        spatial_shapes = {
            name: read_window_sizes(modalities, data_param)
            for (name, modalities) in source_names.items()}
        shapes = {
            name: complete_partial_window_sizes(
                spatial_shapes[name], image_shapes[name])
            for name in input_names}
        # create ImageWindow instance
        return cls(names=input_names,
                   shapes=shapes,
                   dtypes=image_dtypes)

    def set_spatial_shape(self, spatial_window):
        try:
            spatial_window = map(int, spatial_window)
        except ValueError:
            tf.logging.fatal("spatial window should be an array of int")
            raise
        self.shapes = {
            name: complete_partial_window_sizes(
                spatial_window, self.shapes[name])
            for name in self.names}
        # update based on the latest spatial shapes
        self.has_dynamic_shapes = self._check_dynamic_shapes()

    def placeholders_dict(self, n_samples=1):
        """
        This function create a dictionary with items of {name: placeholders}
        name should match the queue input names
        placeholders corresponds to the image window data
        for each of these items an additional {location_name: placeholders}
        is created to hold the spatial location of the image window data
        :param n_samples: specifies the number of image windows
        :return: a dictionary with window data and locations placeholders
        """

        if self._placeholders_dict is not None:
            return self._placeholders_dict

        # batch size=1 if the shapes are dynamic
        self.n_samples = 1 if self.has_dynamic_shapes else n_samples

        names = list(self.names)
        placeholders = [
            tf.placeholder(dtype=self.dtypes[name],
                           shape=[n_samples] + list(self.shapes[name]),
                           name=name)
            for name in names]
        # extending names with names of coordinates
        names.extend([LOCATION_FORMAT.format(name) for name in names])
        # extending placeholders with names of coordinates
        location_shape = [n_samples, 1 + N_SPATIAL * 2]
        placeholders.extend(
            [tf.placeholder(dtype=BUFFER_POSITION_DTYPE,
                            shape=location_shape,
                            name=name)
             for name in self.names])
        self._placeholders_dict = dict(zip(names, placeholders))
        return self._placeholders_dict

    def coordinates_placeholder(self, name):
        return self._placeholders_dict[LOCATION_FORMAT.format(name)]

    def image_data_placeholder(self, name):
        return self._placeholders_dict[name]

    def _check_dynamic_shapes(self):
        """
        Check whether the shape of the window is fully specified
        :return: True indicates it's dynamic, False indicates
         the window size is fully specified.
        """
        for (name, shape) in self.shapes.items():
            for dim_length in shape:
                if not dim_length:
                    return True
        return False

    def match_image_shapes(self, image_shapes):
        if self.has_dynamic_shapes:
            static_window_shapes = self.shapes.copy()
            # fill the None element in dynamic shapes using image_sizes
            for name in self.names:
                static_window_shapes[name] = tuple(
                    win_size if win_size else image_shape
                    for (win_size, image_shape) in
                    zip(list(self.shapes[name]), image_shapes[name]))
        else:
            static_window_shapes = self.shapes
        return static_window_shapes


def read_window_sizes(input_mod_list, input_data_param):
    # read window_size from config dict
    # group them based on output names
    window_sizes = [input_data_param[input_name].spatial_window_size
                    for input_name in input_mod_list]
    if not all(window_sizes):
        window_sizes = filter(None, window_sizes)
    uniq_window_set = set(window_sizes)
    if len(uniq_window_set) > 1:
        tf.logging.info("trying to combine input sources "
                        "with different window sizes: {}".format(window_sizes))
        raise NotImplementedError
    if uniq_window_set:
        return tuple(map(int, uniq_window_set.pop()))
    else:
        return ()


def complete_partial_window_sizes(win_size, img_size):
    img_ndims = len(img_size)
    # crop win_size list if it's longer than img_size
    win_size = list(win_size[:img_ndims])
    while len(win_size) < N_SPATIAL:
        win_size.append(-1)
    # complete win_size list if it's shorter than img_size
    while len(win_size) < img_ndims:
        win_size.append(img_size[len(win_size)])
    # replace zero with full length in the n-th dim of image
    win_size = [win if win > 0 else None for win in win_size]
    return tuple(win_size)