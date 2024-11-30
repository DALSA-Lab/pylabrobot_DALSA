from pylabrobot.resources.carrier import (
  Coordinate,
<<<<<<< HEAD
  CarrierSite,
  TroughCarrier,
  create_homogeneous_carrier_sites,
=======
  ResourceHolder,
  TroughCarrier,
  create_homogeneous_resources,
>>>>>>> upstream/main
)


def Trough_CAR_4R200_A00(name: str) -> TroughCarrier:
  """Hamilton cat. no.: 185436
  Hamilton name: 'RGT_CAR_4R200_A00'.
  Trough carrier for 4x 200ml troughs. 2 tracks(T) wide.
  - Material: ? (recognisable via cLLD)
  - Sterilization_compatibility: ?

  carrier_site_pedestal_top = 134
  carrier_site_pedestal_bottom = 132.5
  pedestal_z_height = 1.5
  true_dz = 1.2
  trought_z_thickness = 1.4
  """
  return TroughCarrier(
    name=name,
    size_x=45.0,
    size_y=497.0,
    size_z=71.5,
    # pedestal_size_z=1.5 mm
<<<<<<< HEAD
    sites=create_homogeneous_carrier_sites(
      klass=CarrierSite,
=======
    sites=create_homogeneous_resources(
      klass=ResourceHolder,
>>>>>>> upstream/main
      locations=[
        Coordinate(4.0, 2.0, 34.0 + 1.5),
        Coordinate(4.0, 123.0, 34.0 + 1.5),  # TODO: properly define troughs to remove dependency
        Coordinate(4.0, 245.0, 34.0 + 1.5),  # on this 1.5mm offset (material_z_thickness)
        Coordinate(4.0, 366.0, 34.0 + 1.5),
      ],
<<<<<<< HEAD
      site_size_x=37.0,
      site_size_y=118.0,
=======
      resource_size_x=37.0,
      resource_size_y=118.0,
>>>>>>> upstream/main
    ),
    model="Trough_CAR_4R200_A00",
  )
