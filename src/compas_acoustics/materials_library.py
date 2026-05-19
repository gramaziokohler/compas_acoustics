from compas.data import Data
from compas.data import json_load

from compas_acoustics.defaults import Defaults
from compas_acoustics.acoustic_material import AcousticMaterial

import os


__all__ = ['MaterialsLibrary']


class MaterialsLibrary(Data):
    """
    A class for handling acoustic materials.
    """


    def __init__(self):
        self._library_path = Defaults().MATERIALS_LIBRARY_PATH
    
    
    def _load_materials_from_file(self, path: str) -> list:
        """Load materials from a JSON file, returning a list regardless of whether
        the file contains a single material or multiple materials."""
        result = json_load(path)
        if isinstance(result, list):
            return result
        return [result]


    def material_from_name(self, material_name: str) -> AcousticMaterial:
        """Retrieve an AcousticMaterial instance by its name.
        
        Parameters
        ----------
        material_name : str
            The identifier of the acoustic material.
        
        Returns
        -------
        AcousticMaterial
            An instance of AcousticMaterial.
        
        Raises
        ------
        KeyError
            If no material with the given name is found.
        """
        for f in os.listdir(self._library_path):
            if not f.endswith('.json'):
                continue
            path = os.path.join(self._library_path, f)
            for material in self._load_materials_from_file(path):
                if material.name == material_name:
                    return material
        raise KeyError(f"Material '{material_name}' not found in library.")
    
    
    def material_from_json(self, path: str) -> list:
        """Load materials from a JSON file.
        
        Parameters
        ----------
        path : str
            The path to the JSON file containing one or more material definitions.
        
        Returns
        -------
        list
            A list of AcousticMaterial instances.
        """
        return self._load_materials_from_file(path)


    def path_from_material_name(self, material_name: str) -> str:
        """Find the path to the JSON file that contains a material by its name.
        
        Parameters
        ----------
        material_name : str
            The identifier of the acoustic material.
        
        Returns
        -------
        str
            The path to the JSON file containing the specified material.
        
        Raises
        ------
        KeyError
            If no material with the given name is found.
        """
        for f in os.listdir(self._library_path):
            if not f.endswith('.json'):
                continue
            path = os.path.join(self._library_path, f)
            for material in self._load_materials_from_file(path):
                if material.name == material_name:
                    return path
        raise KeyError(f"Material '{material_name}' not found in library.")


    def material_names(self, material_type: [str] = None) -> list:
        """List of all material names in the library.

        Parameters
        ----------
        material_type : List [str]
            Filter depending on the type of material: "absorption", "scattering", "transmission". E.g. [scattering, transmission] will look for materials that have scattering coefficients OR transmission coefficients.
        
        Returns
        -------
        list
            A list of material names.
        """
        names = []
        for f in os.listdir(self._library_path):
            if not f.endswith('.json'):
                continue
            path = os.path.join(self._library_path, f)
            for material in self._load_materials_from_file(path):
                if material_type:
                    if "absorption" in material_type:
                        if material.absorption_coefficients is not None:
                            names.append(material.name)
                    if "scattering" in material_type:
                        if material.scattering_coefficients is not None:
                            names.append(material.name)
                    if "transmission" in material_type:
                        if material.transmission_coefficients is not None:
                            names.append(material.name)
        return names
    
    