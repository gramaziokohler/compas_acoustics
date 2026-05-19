import os
import math
import warnings

from compas.data import Data
from compas_acoustics.defaults import Defaults

__all__ = ['AcousticMaterial']


class AcousticMaterial(Data):
    """Class representing an acoustic material with its properties.
    
    Parameters
    ----------
    name : str
        The name of the acoustic material. Lowercase and no spaces.
    description : str
        A text describing the material.
    absorption_coefficients : list
        A list of absorption coefficients corresponding to frequency bands.
    scattering_coefficients : list
        A list of scattering coefficients corresponding to frequency bands. Optional.
    transmission_coefficients : list
        A list of transmission coefficients corresponding to frequency bands. Optional.
    """
    
    def __init__(self, name: str, absorption_coefficients = None, scattering_coefficients = None, transmission_coefficients = None, frequency_bands: list = None, resize_bands: str = 'intersection', description: str = None):
        super().__init__()
        self.name = name
        self.description = description

        # Resolve any string parameters by looking up the library
        abs_coeffs, abs_freqs = self._resolve_coefficients_from_library(absorption_coefficients, 'absorption')
        scat_coeffs, scat_freqs = self._resolve_coefficients_from_library(scattering_coefficients, 'scattering')
        trans_coeffs, trans_freqs = self._resolve_coefficients_from_library(transmission_coefficients, 'transmission')

        # Collect frequency bands sourced from library lookups (only where coefficients are present)
        lib_freq_sources = [
            (coeffs, freqs)
            for coeffs, freqs in [(abs_coeffs, abs_freqs), (scat_coeffs, scat_freqs), (trans_coeffs, trans_freqs)]
            if freqs is not None and coeffs is not None
        ]

        # Determine final frequency bands: explicit > derived from library > default
        if frequency_bands is not None:
            resolved_frequency_bands = frequency_bands
        elif lib_freq_sources:
            all_freqs = [freqs for _, freqs in lib_freq_sources]
            if len(set(tuple(f) for f in all_freqs)) == 1:
                resolved_frequency_bands = all_freqs[0]
            else:
                # Multiple string sources with different bands: align using intersection or union
                if resize_bands == 'union':
                    resolved_frequency_bands = sorted(set().union(*all_freqs))
                else:  # default: intersection
                    resolved_frequency_bands = sorted(set(all_freqs[0]).intersection(*all_freqs[1:]))
                # Trim each library-sourced coefficient list to the resolved bands
                if abs_freqs is not None and abs_coeffs is not None:
                    abs_coeffs = self._trim_coefficients(abs_coeffs, abs_freqs, resolved_frequency_bands)
                if scat_freqs is not None and scat_coeffs is not None:
                    scat_coeffs = self._trim_coefficients(scat_coeffs, scat_freqs, resolved_frequency_bands)
                if trans_freqs is not None and trans_coeffs is not None:
                    trans_coeffs = self._trim_coefficients(trans_coeffs, trans_freqs, resolved_frequency_bands)
        else:
            resolved_frequency_bands = None

        self.frequency_bands = resolved_frequency_bands
        self.absorption_coefficients = abs_coeffs
        self.scattering_coefficients = scat_coeffs
        self.transmission_coefficients = trans_coeffs 
        
    
    @property
    def name(self):
        return self._name
    
    
    @name.setter
    def name(self, name):
        if " " in name:
            raise ValueError("Material name cannot contain spaces.")
        if any(char.isupper() for char in name):
            raise ValueError("Material name must be lowercase.")
        self._name = name
        
        
    @property
    def description(self):
        return self._description
    
    
    @description.setter
    def description(self, description):
        self._description = description

    
    @property
    def absorption_coefficients(self):
        return self._absorption_coefficients
    
    
    @absorption_coefficients.setter
    def absorption_coefficients(self, coefficients):
        if coefficients:
            self._absorption_coefficients = self._sanitize_coefficients(coefficients, "Absorption")
        else:
            self._absorption_coefficients = None
        
    
    @property
    def scattering_coefficients(self):
        return self._scattering_coefficients
    
    
    @scattering_coefficients.setter
    def scattering_coefficients(self, coefficients):
        if coefficients:
            self._scattering_coefficients = self._sanitize_coefficients(coefficients, "Scattering")
        else:
            self._scattering_coefficients = None
    
    
    @property
    def transmission_coefficients(self):
        return self._transmission_coefficients
    
    
    @transmission_coefficients.setter
    def transmission_coefficients(self, coefficients):
        if coefficients:
            self._transmission_coefficients = self._sanitize_coefficients(coefficients, "Transmission")
        else:
            self._transmission_coefficients = None
            
    
    @property
    def frequency_bands(self):
        return self._frequency_bands
    
    
    @frequency_bands.setter
    def frequency_bands(self, frequency_bands):
        if frequency_bands:
            self._frequency_bands = frequency_bands
        else:
            self._frequency_bands = Defaults().DEFAULT_FREQUENCY_BANDS
    
        
    def scattering_coefficients_from_depth(self, depth, s_max=0.8, c = Defaults().DEFAULT_SPEED_OF_SOUND):
        """
        Compute scattering coefficients for octave bands
        based on surface depth using a wavelength-dependent model.
        
        Based on research from:
        1. Dalenbäck, B.-I. L. (1995). Room acoustic prediction and auralization—How close can we get to reality?
        Proceedings of the 15th International Congress on Acoustics (ICA), Trondheim, Norway.
        2. Pätynen, J., & Lokki, T. (2010). Directivities of symphony orchestra instruments and their effect on recorded spatial sound.
        Acta Acustica united with Acustica, 96(1).
        
        Parameters
        ----------
        depth : float
            Characteristic surface depth or roughness (in meters).
        s_max : float, optional
            Maximum scattering coefficient (default = 0.8).
        c : float, optional
            Speed of sound in air (m/s), default = 343.

        Returns
        -------
        list of float
            List of scattering coefficients.
        """
        if depth > 2:
            warnings.warn(f"Depth value should be in meters! Calculating scattering coefficients for depth {depth} meters.")
        
        freq_bands = self.frequency_bands
        
        coeffs = []
        for f in freq_bands:
            k = 2 * math.pi * f / c
            s = s_max * (1 - math.exp(-(k * depth)**2))
            coeffs.append((round(s, 3)))
            
        self.scattering_coefficients = coeffs

        return self.scattering_coefficients   
            
            
    @staticmethod
    def _resolve_coefficients_from_library(value, coeff_type: str):
        """If value is a string, look up the material in the library and return
        (coefficients_list, frequency_bands). Otherwise return (value, None)."""
        if not isinstance(value, str):
            return value, None
        from compas_acoustics.materials_library import MaterialsLibrary
        material = MaterialsLibrary().material_from_name(value)
        freqs = material.frequency_bands
        if coeff_type == 'absorption':
            return material.absorption_coefficients, freqs
        elif coeff_type == 'scattering':
            return material.scattering_coefficients, freqs
        elif coeff_type == 'transmission':
            return material.transmission_coefficients, freqs
        return None, freqs


    @staticmethod
    def _trim_coefficients(coefficients: list, source_freqs: list, target_freqs: list) -> list:
        """Trim a coefficient list to match target_freqs using nearest-neighbour matching
        (same logic as resample_frequency_bands)."""
        result = []
        for target in target_freqs:
            closest_index = min(range(len(source_freqs)), key=lambda i: abs(source_freqs[i] - target))
            result.append(coefficients[closest_index])
        return result


    def _sanitize_coefficients(self, coefficients, coeff_type:str):
        if isinstance(coefficients, int) or isinstance(coefficients, float):
                coefficients = [coefficients] * len(self.frequency_bands)
        elif isinstance(coefficients, (list, tuple)):
            if len(coefficients) != len(self.frequency_bands):
                raise ValueError(f"{coeff_type} coefficients list must have {len(self.frequency_bands)} values corresponding to the frequency bands.")
            else:
                coefficients = list(coefficients)
        return coefficients
    
    
    def add_to_library(self):
        """
        Add the AcousticMaterial to the library.
        """
        #TODO check if material with same name exists
        #TODO check if material with same properties exists
        path = os.path.join(Defaults().MATERIALS_LIBRARY_PATH, f"{self.name}.json")
        self.to_json(path, compact=True, minimal=True)

    def resample_frequency_bands(self, frequency_bands):
        """Resample all coefficient lists to a new set of frequency bands using
        nearest-neighbour matching. Works for both truncation and extrapolation.
        
        #TODO interpolate values when new center frequencies differ from standard ones.
        """
        old_frequency_bands = self.frequency_bands
        new_abs = self._trim_coefficients(self.absorption_coefficients, old_frequency_bands, frequency_bands) if self.absorption_coefficients is not None else None
        new_scat = self._trim_coefficients(self.scattering_coefficients, old_frequency_bands, frequency_bands) if self.scattering_coefficients is not None else None
        new_trans = self._trim_coefficients(self.transmission_coefficients, old_frequency_bands, frequency_bands) if self.transmission_coefficients is not None else None
        self.frequency_bands = frequency_bands
        self.absorption_coefficients = new_abs
        self.scattering_coefficients = new_scat
        self.transmission_coefficients = new_trans
        print(f"Acoustic material {self.name} got redefined from {old_frequency_bands} to {frequency_bands}. Resulting {self} ")
        


    @property
    def __data__(self):
        return{
            "name": self.name,
            "description": self.description or "",
            "absorption_coefficients": self.absorption_coefficients or [],
            "scattering_coefficients": self.scattering_coefficients or [],
            "transmission_coefficients": self.transmission_coefficients or [],
        }
        
  
    def __str__(self):
        return f"AcousticMaterial(name={self.name}, absorption_coefficients={self.absorption_coefficients}, scattering_coefficients={self.scattering_coefficients}, transmission_coefficients={self.transmission_coefficients})"
    