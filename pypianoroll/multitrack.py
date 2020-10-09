"""Multitrack class.

This module defines the core class of Pypianoroll---the Multitrack
class, a container for multitrack piano rolls.

"""
from copy import deepcopy
from typing import List, Optional

import numpy as np
import pretty_midi
from numpy import ndarray

from .outputs import save, to_pretty_midi, write
from .track import Track
from .visualization import plot_multitrack

__all__ = ["Multitrack"]

DEFAULT_RESOLUTION = 24
DEFAULT_TEMPO = 120


class Multitrack:
    """A container for multitrack piano rolls.

    This is the core class of Pypianoroll.

    Attributes
    ----------
    resolution : int
        Time steps per quarter note.
    tempo : ndarray, dtype={int, float}, shape=(?, 1), optional
        Tempo (in qpm) at each time step. The length is the total
        number of time steps.
    downbeat : ndarray, dtype=bool, shape=(?, 1), optional
        A boolean array that indicates whether the time step contains a
        downbeat (i.e., the first time step of a bar). The length is the
        total number of time steps.
    name : str, optional
        Multitrack name.
    tracks : list of :class:`pypianoroll.Track`, optional
        Music tracks.

    """

    def __init__(
        self,
        resolution: Optional[int] = None,
        tempo: Optional[ndarray] = None,
        downbeat: Optional[ndarray] = None,
        name: Optional[str] = None,
        tracks: Optional[List[Track]] = None,
    ):
        self.resolution = (
            resolution if resolution is not None else DEFAULT_RESOLUTION
        )

        self.tempo = np.asarray(tempo) if tempo is not None else None

        if downbeat is None:
            self.downbeat = None
        else:
            downbeat = np.asarray(downbeat)
            if np.issubdtype(downbeat.dtype, np.integer):
                self.downbeat = np.zeros((max(downbeat) + 1, 1), bool)
                self.downbeat[downbeat] = True
            else:
                self.downbeat = downbeat

        self.name = name
        self.tracks = tracks if tracks is not None else []

    def __len__(self):
        return len(self.tracks)

    def __getitem__(self, val):
        if isinstance(val, tuple):
            if isinstance(val[0], int):
                tracks = [self.tracks[val[0]][val[1:]]]
            elif isinstance(val[0], list):
                tracks = [self.tracks[i][val[1:]] for i in val[0]]
            else:
                tracks = [track[val[1:]] for track in self.tracks[val[0]]]

            if self.downbeat is not None:
                downbeat = self.downbeat[val[1]]
            else:
                downbeat = None

            if self.tempo is not None:
                tempo = self.tempo[val[1]]
            else:
                tempo = None

            return Multitrack(
                tracks=tracks,
                tempo=tempo,
                downbeat=downbeat,
                resolution=self.resolution,
                name=self.name,
            )

        if isinstance(val, list):
            tracks = [self.tracks[i] for i in val]
        else:
            tracks = self.tracks[val]

        return Multitrack(
            tracks=tracks,
            tempo=self.tempo,
            downbeat=self.downbeat,
            resolution=self.resolution,
            name=self.name,
        )

    def __repr__(self):
        to_join = []
        if self.name is not None:
            to_join.append("name=" + repr(self.name))
        to_join.append("resolution=" + repr(self.resolution))
        if self.tempo.size:
            to_join.append("tempo=[" + repr(self.tempo[0]) + ", ...]")
        if self.downbeat.size:
            to_join.append("downbeat=[" + repr(self.downbeat[0]) + ", ...]")
        if self.tracks:
            to_join.append("tracks=" + repr(self.tracks))
        return "Multitrack(" + ", ".join(to_join) + ")"

    def validate(self):
        """Raise a proper error if any attribute is invalid."""
        # Resolution
        if not isinstance(self.resolution, int):
            raise TypeError("`resolution` must be of type int.")
        if self.resolution < 1:
            raise ValueError("`resolution` must be a positive integer.")

        # Tempo
        if not isinstance(self.tempo, np.ndarray):
            raise TypeError("`tempo` must be a NumPy array.")
        if not np.issubdtype(self.tempo.dtype, np.number):
            raise TypeError(
                "Data type of `tempo` must be a subdtype of np.number."
            )
        if self.tempo.ndim != 1:
            raise ValueError("`tempo` must be a 1D NumPy array.")
        if np.any(self.tempo <= 0.0):
            raise ValueError("`tempo` should contain only positive numbers.")

        # Downbeat
        if self.downbeat is not None:
            if not isinstance(self.downbeat, np.ndarray):
                raise TypeError("`downbeat` must be a NumPy array.")
            if not np.issubdtype(self.downbeat.dtype, np.bool_):
                raise TypeError("Data type of `downbeat` must be bool.")
            if self.downbeat.ndim != 1:
                raise ValueError("`downbeat` must be a 1D NumPy array.")

        # Name
        if not isinstance(self.name, str):
            raise TypeError("`name` must be of type str.")

        # Tracks
        for track in self.tracks:
            if not isinstance(track, Track):
                raise TypeError(
                    "`tracks` must be a list of `pypianoroll.Track` instances."
                )
            track.validate()

    def is_binarized(self):
        """Return True if piano rolls are binarized, otherwise False."""
        for track in self.tracks:
            if not track.is_binarized():
                return False
        return True

    def get_active_length(self):
        """Return the maximum active length of the piano rolls.

        The active length is defined as the length of the piano roll
        without trailing silence.

        Returns
        -------
        int
            maximum active length of the piano rolls (in time steps).

        """
        active_length = 0
        for track in self.tracks:
            now_length = track.get_active_length()
            if active_length < track.get_active_length():
                active_length = now_length
        return active_length

    def get_active_pitch_range(self):
        """Return the active pitch range as a tuple (lowest, highest).

        Returns
        -------
        lowest : int
            Lowest active pitch in all the piano rolls.
        highest : int
            Highest active pitch in all the piano rolls.

        """
        lowest, highest = self.tracks[0].get_active_pitch_range()
        if len(self.tracks) > 1:
            for track in self.tracks[1:]:
                low, high = track.get_active_pitch_range()
                if low < lowest:
                    lowest = low
                if high > highest:
                    highest = high
        return lowest, highest

    def get_downbeat_steps(self):
        """Return the indices of time steps that contain downbeats.

        Returns
        -------
        downbeat_steps : list
            Indices of time steps that contain downbeats.

        """
        if self.downbeat is None:
            return []
        downbeat_steps = np.nonzero(self.downbeat)[0].tolist()
        return downbeat_steps

    def get_empty_tracks(self):
        """Return the indices of tracks with empty piano rolls.

        Returns
        -------
        list
            Indices of tracks with empty piano rolls.

        """
        indices = []
        for i, track in enumerate(self.tracks):
            if not np.any(track.pianoroll):
                indices.append(i)
        return indices

    def get_max_length(self):
        """Return the maximum length of the piano rolls (in time steps).

        Returns
        -------
        max_length : int
            Maximum length of the piano rolls (in time step).

        """
        max_length = 0
        for track in self.tracks:
            if max_length < track.pianoroll.shape[0]:
                max_length = track.pianoroll.shape[0]
        return max_length

    def get_merged_pianoroll(self, mode: str = "sum"):
        """Return the merged piano roll.

        Parameters
        ----------
        mode : {'sum', 'max', 'any'}
            Merging strategy to apply along the track axis.
            Defaults to 'sum'.

            - In 'sum' mode, the merged piano roll is the sum of all the
              piano rolls. Note that for binarized piano rolls, integer
              summation is performed.
            - In 'max' mode, for each pixel, the maximum value among
              all the piano rolls is assigned to the merged piano roll.
            - In 'any' mode, the value of a pixel in the merged piano
              roll is True if any of the piano rolls has nonzero value
              at that pixel; False if all piano rolls are inactive
              (zero-valued) at that pixel.

        Returns
        -------
        ndarray, shape=(?, 128)
            Merged piano roll.

        """
        stacked = self.get_stacked_pianoroll()

        if mode == "any":
            merged = np.any(stacked, axis=2)
        elif mode == "sum":
            merged = np.sum(stacked, axis=2)
        elif mode == "max":
            merged = np.max(stacked, axis=2)
        else:
            raise ValueError("`mode` must be one of {'max', 'sum', 'any'}.")

        return merged

    def get_stacked_pianoroll(self):
        """Return a stacked multitrack piano-roll as a tensor.

        The shape of the return array is (n_time_steps, 128, n_tracks).

        Returns
        -------
        ndarray, shape=(?, 128, ?)
            Stacked piano roll.

        """
        multitrack = deepcopy(self)
        multitrack.pad_to_same()
        stacked = np.stack(
            [track.pianoroll for track in multitrack.tracks], -1
        )
        return stacked

    def append(self, track: Track):
        """Append a Track object to the track list.

        Parameters
        ----------
        track : :class:`pypianoroll.Track`
            Track to append to the track list.

        """
        self.tracks.append(track)
        return self

    def assign_constant(self, value: float):
        """Assign a constant value to all nonzero entries.

        If a piano roll is not binarized, its data type will be
        preserved. If a piano roll is binarized, cast it to the dtype
        of `value`.

        Arguments
        ---------
        value : int or float
            Value to assign to all the nonzero entries in the piano
            rolls.

        """
        for track in self.tracks:
            track.assign_constant(value)

    def binarize(self, threshold: float = 0):
        """Binarize the piano rolls.

        Parameters
        ----------
        threshold : int or float
            Threshold to binarize the piano rolls. Defaults to zero.

        """
        for track in self.tracks:
            track.binarize(threshold)
        return self

    def clip(self, lower: float = 0, upper: float = 127):
        """Clip the piano rolls by a lower bound and an upper bound.

        Parameters
        ----------
        lower : int or float
            Lower bound to clip the piano rolls. Defaults to 0.
        upper : int or float
            Upper bound to clip the piano rolls. Defaults to 127.

        """
        for track in self.tracks:
            track.clip(lower, upper)
        return self

    def downsample(self, factor: int):
        """Downsample the piano rolls by the given factor.

        Attribute `resolution` will be updated accordingly as well.

        Parameters
        ----------
        factor : int
            Ratio of the original resolution to the desired resolution.

        """
        if self.resolution % factor > 0:
            raise ValueError(
                "Downsample factor must be a factor of the resolution."
            )
        self.resolution = self.resolution // factor
        for track in self.tracks:
            track.pianoroll = track.pianoroll[::factor]
        return self

    def count_downbeat(self):
        """Return the number of down beats.

        The return value is calculated based solely on attribute
        `downbeat`.

        Returns
        -------
        int
            Number of down beats.

        """
        return np.count_nonzero(self.downbeat)

    def merge_tracks(
        self,
        track_indices: Optional[List[int]] = None,
        mode: str = "sum",
        program: int = 0,
        is_drum: bool = False,
        name: str = "merged",
        remove_source: bool = False,
    ):
        """Merge certain tracks into a single track.

        Merge the piano rolls of certain tracks (specified by
        `track_indices`). The merged track will be appended to the end
        of the track list.

        Parameters
        ----------
        track_indices : list
            Indices of tracks to be merged. Defaults to merge all the
            tracks.
        mode : {'sum', 'max', 'any'}
            A string that indicates the merging strategy to apply along
            the track axis. Default to 'sum'.

            - In 'sum' mode, the merged piano roll is the sum of
              the collected piano rolls. Note that for binarized piano
              rolls, integer summation is performed.
            - In 'max' mode, for each pixel, the maximum value among
              the collected piano rolls is assigned to the merged piano
              roll.
            - In 'any' mode, the value of a pixel in the merged piano
              roll is True if any of the collected piano rolls has
              nonzero value at that pixel; False if all the collected
              piano rolls are inactive (zero-valued) at that pixel.

        program : int, 0-127, optional
            Program number according to General MIDI specification [1].
            Defaults to 0 (Acoustic Grand Piano).
        is_drum : bool, optional
            Whether it is a percussion track. Defaults to False.
        name : str, optional
            Track name. Defaults to `merged`.
        remove_source : bool
            Whether to remove the source tracks from the track list.
            Defaults to False.

        References
        ----------
        1. https://www.midi.org/specifications/item/gm-level-1-sound-set

        """
        if mode not in ("max", "sum", "any"):
            raise ValueError("`mode` must be one of {'max', 'sum', 'any'}.")

        merged = self[track_indices].get_merged_pianoroll(mode)

        merged_track = Track(
            program=program, is_drum=is_drum, name=name, pianoroll=merged
        )
        self.tracks.append(merged_track)

        if remove_source:
            if track_indices is None:
                self.remove_tracks(list(range(len(self.tracks) - 1)))
            else:
                self.remove_tracks(track_indices)

        return self

    def pad(self, pad_length):
        """Pad the piano rolls with zeros.

        Notes
        -----
        The lengths of the resulting piano rolls are not guaranteed to
        be the same. See :meth:`pypianoroll.Multitrack.pad_to_same`.

        Parameters
        ----------
        pad_length : int
            Length to pad along the time axis with zeros.

        """
        for track in self.tracks:
            track.pad(pad_length)
        return self

    def pad_to_multiple(self, factor: int):
        """Pad the piano rolls along the time axis to a multiple.

        Pad the piano rolls with zeros at the end along the time axis
        of the minimum length that makes the lengths of the resulting
        piano rolls multiples of `factor`.

        Notes
        -----
        The resulting piano roll lengths are not guaranteed to be the
        same. See :meth:`pypianoroll.Multitrack.pad_to_same`.

        Parameters
        ----------
        factor : int
            The value which the length of the resulting piano rolls will
            be a multiple of.

        """
        for track in self.tracks:
            track.pad_to_multiple(factor)
        return self

    def pad_to_same(self):
        """Pad piano rolls along the time axis to have the same length.

        Pad shorter piano rolls with zeros at the end along the time
        axis so that the resulting piano rolls have the same length.

        """
        max_length = self.get_max_length()
        for track in self.tracks:
            if track.pianoroll.shape[0] < max_length:
                track.pad(max_length - track.pianoroll.shape[0])
        return self

    def remove_empty_tracks(self):
        """Remove tracks with empty pianorolls."""
        self.remove_tracks(self.get_empty_tracks())

    def remove_tracks(self, track_indices: List[int]):
        """Remove certain tracks.

        Parameters
        ----------
        track_indices : list
            Indices of the tracks to remove.

        """
        if isinstance(track_indices, int):
            track_indices = [track_indices]
        self.tracks = [
            track
            for idx, track in enumerate(self.tracks)
            if idx not in track_indices
        ]
        return self

    def transpose(self, semitone: int):
        """Transpose the piano rolls by a number of semitones.

        Positive values are for a higher key, while negative values are
        for a lower key. Drum tracks are ignored.

        Parameters
        ----------
        semitone : int
            Number of semitones to transpose the piano rolls.

        """
        for track in self.tracks:
            if not track.is_drum:
                track.transpose(semitone)

    def trim_trailing_silence(self):
        """Trim the trailing silences of the piano rolls.

        All the piano rolls will have the same length after the
        trimming.

        """
        active_length = self.get_active_length()
        for track in self.tracks:
            track.pianoroll = track.pianoroll[:active_length]
        return self

    def save(self, path: str, compressed: bool = True):
        """Save to a NPZ file.

        Refer to :func:`pypianoroll.save` for full documentation.

        """
        save(path, self, compressed=compressed)

    def to_pretty_midi(self, **kwargs):
        """Return as a PrettyMIDI object.

        Refer to :func:`pypianoroll.to_pretty_midi` for full
        documentation.

        """
        return to_pretty_midi(self, **kwargs)

    def write(self, path: str):
        """Write to a MIDI file.

        Refer to :func:`pypianoroll.write` for full documentation.

        """
        return write(path, self)

    def plot(self, **kwargs):
        """Plot the multitrack and/or save a plot of it.

        Refer to :func:`pypianoroll.plot_multitrack` for full
        documentation.

        """
        return plot_multitrack(self, **kwargs)
