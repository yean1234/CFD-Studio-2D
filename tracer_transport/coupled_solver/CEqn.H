// ClO2 dilute passive species: no release, reaction, sorption or solutal buoyancy.
// Lee et al. (2015), DOI 10.1016/j.jfoodeng.2014.07.008.
// Linear interpolation is a stated assumption; no out-of-range extrapolation.
{
    if (gMin(T.primitiveField()) < 278.15 || gMax(T.primitiveField()) > 313.15)
        FatalErrorInFunction << "Temperature outside 5..40 C diffusivity data" << exit(FatalError);
    forAll(T, celli)
    {
        const scalar tc = T[celli] - 273.15;
        molecularD[celli] = tc <= 23
            ? 1.29e-5 + (tc-5)*(1.45e-5-1.29e-5)/18
            : 1.45e-5 + (tc-23)*(1.73e-5-1.45e-5)/17;
    }
    // No species flux across external walls; coefficients interpolated to faces.
    volScalarField DEff("DEff", diffusionFactor*molecularD + freeGas*turbulence->nut()/Sct);
    fvScalarMatrix CEqn
    (
        fvm::ddt(eps, C) + fvm::div(phi, C) - fvm::laplacian(DEff, C)
    );
    CEqn.solve();
}
