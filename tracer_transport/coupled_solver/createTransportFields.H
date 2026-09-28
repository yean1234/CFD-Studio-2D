// CFD Studio additions, GPL-3.0-or-later; see COPYING and README.md.
// U is a divergence-free superficial velocity in a Brinkman penalty model.
#define READ_STATIC_FIELD(name) \
    volScalarField name(IOobject(#name, runTime.timeName(), mesh, \
        IOobject::MUST_READ, IOobject::NO_WRITE), mesh)
READ_STATIC_FIELD(eps);
READ_STATIC_FIELD(drag);
READ_STATIC_FIELD(heatCapacityRatio);
READ_STATIC_FIELD(alphaBulk);
READ_STATIC_FIELD(diffusionFactor);
READ_STATIC_FIELD(freeGas);
#undef READ_STATIC_FIELD
volScalarField C(IOobject("C", runTime.timeName(), mesh,
    IOobject::MUST_READ, IOobject::AUTO_WRITE), mesh);
IOdictionary coupling(IOobject("couplingProperties", runTime.constant(), mesh,
    IOobject::MUST_READ, IOobject::NO_WRITE));
const dimensionedScalar airRhoCp("airRhoCp", dimEnergy/dimVolume/dimTemperature, coupling);
const scalar Sct = coupling.get<scalar>("Sct");
volScalarField kappa(IOobject("kappa", runTime.timeName(), mesh,
    IOobject::NO_READ, IOobject::NO_WRITE), airRhoCp*alphaBulk);
volScalarField molecularD(IOobject("molecularD", runTime.timeName(), mesh),
    mesh, dimensionedScalar("D", dimViscosity, 1.45e-5));
scalar cumulativeHeat = 0;
const scalar initialHeat = fvc::domainIntegrate(heatCapacityRatio*T).value();
mesh.setFluxRequired(T.name());
// Independent geometry outputs; never overwrite the species field C.
volVectorField cellCentres(IOobject("cellCentres", runTime.timeName(), mesh,
    IOobject::NO_READ, IOobject::NO_WRITE), mesh.C());
cellCentres.write();
volScalarField cellVolumes(IOobject("cellVolumes", runTime.timeName(), mesh,
    IOobject::NO_READ, IOobject::NO_WRITE), mesh, dimensionedScalar("V", dimVolume, 0));
cellVolumes.primitiveFieldRef() = mesh.V();
cellVolumes.write();
