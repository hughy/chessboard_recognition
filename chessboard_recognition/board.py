from copy import deepcopy
from typing import Tuple

from PIL import Image
import numpy as np
import tensorflow as tf


def get_cropped_board_image(input_path: str) -> tf.Tensor:
    """Loads an image and crops it at the detected chessboard edges.
    """
    input_img = Image.open(input_path)
    img = preprocess_image(input_img)
    return crop_board_image(img)


def preprocess_image(input_img: Image) -> tf.Tensor:
    """Preprocess the input image.
    """
    img = deepcopy(input_img)
    # Convert to grayscale
    img = img.convert(mode="L")
    # Convert to array
    img = np.array(img)
    # Convert to 4-D
    img = np.reshape(img, (1, *img.shape, 1))
    # Convert to tensor
    return tf.constant(img, dtype=tf.float32)


def crop_board_image(img: tf.Tensor) -> tf.Tensor:
    """Detect chessboard gridlines in the input image and crop to the board edges.
    """
    # Identify gridline indices
    horiz_indices, vert_indices = _detect_grid_indices(img)
    # Determine length of grid square sides
    square_length = horiz_indices[1] - horiz_indices[0]
    # Crop image to grid squares
    h_start = horiz_indices[0] - square_length
    h_end = horiz_indices[-1] + square_length
    v_start = vert_indices[0] - square_length
    v_end = vert_indices[-1] + square_length
    return img[:, h_start:h_end, v_start:v_end, :]


def _get_board_filters() -> tf.Tensor:
    """Creates a 4-D tensor of filters to identify edges within a chessboard.
    """
    # Create filters
    h_light_dark = np.array([[1, 1, 1], [0, 0, 0], [-1, -1, -1],])
    h_dark_light = np.array([[-1, -1, -1], [0, 0, 0], [1, 1, 1],])
    v_light_dark = np.array([[1, 0, -1], [1, 0, -1], [1, 0, -1],])
    v_dark_light = np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1],])
    # Stack filters
    kernel = np.stack([h_light_dark, h_dark_light, v_light_dark, v_dark_light], axis=-1)
    # Convert to 4-D
    kernel = np.reshape(kernel, (3, 3, 1, 4))
    # Convert to tensor
    return tf.constant(kernel, dtype=tf.float32)


def _detect_grid_indices(img: tf.Tensor) -> Tuple[np.array, np.array]:
    """Detects image indices of chessboard gridlines.
    """
    kernel = _get_board_filters()

    # Apply convolution
    output_img = tf.nn.conv2d(img, kernel, strides=[1, 1, 1, 1], padding="SAME")
    # Clip values to 0-255 range
    output_img = tf.clip_by_value(output_img, 0, 255)
    # Collapse output channels into a single channel
    output_img = tf.math.reduce_max(output_img, axis=-1)
    # Remove first dimension
    output_img = tf.squeeze(output_img, axis=0)

    # Get indices of vertical and horizontal edges
    horiz_lines = _filter_lines(output_img, axis=1)
    vert_lines = _filter_lines(output_img, axis=0)

    return _filter_grid_indices(horiz_lines), _filter_grid_indices(vert_lines)


def _filter_lines(img: tf.Tensor, axis: int) -> tf.Tensor:
    """Finds indices of straight lines detected in the image.
    """
    axis_mean = tf.math.reduce_mean(img, axis=axis)
    # Use 80% of maximum pixel value as threshold
    line_indices = tf.where(axis_mean > (255 / 1.25))
    # Convert to 1-D numpy array
    return tf.squeeze(line_indices, axis=-1)


def _filter_grid_indices(line_indices: tf.Tensor) -> np.array:
    """Finds the indices corresponding to grid lines on the chessboard.
    """
    # Convolution filters create two adjacent lines demarcating grid edges.
    # Use latter index.
    pairs = tf.stack([line_indices[:-1], line_indices[1:]], axis=-1)
    pair_diffs = tf.map_fn(lambda pair: pair[1] - pair[0], pairs)
    possible_indices = tf.boolean_mask(line_indices[1:], pair_diffs > 1)

    return _filter_evenly_spaced_indices(possible_indices.numpy())


def _filter_evenly_spaced_indices(possible_indices: np.array) -> np.array:
    """Finds a list of seven evenly-spaced indices from the input list, if any.
    """
    set_possible_indices = set(possible_indices)
    for start in possible_indices[:-6]:
        for end in list(reversed(possible_indices))[:-6]:
            space_length = (end - start) // 6
            grid_indices = list(range(start, end + 1, space_length))
            set_grid_indices = set(grid_indices)
            if set_grid_indices.issubset(set_possible_indices):
                return np.array(grid_indices)

    raise ValueError("Failed to detect grid lines in chessboard!")
