// Effective single-temperature (local thermal equilibrium) energy balance.
// alphaBulk = bulk conductivity / air volumetric heat capacity.
{
    alphat = turbulence->nut()/Prt;
    alphat.correctBoundaryConditions();
    volScalarField alphaEff("alphaEff", alphaBulk + freeGas*alphat);
    kappa = airRhoCp*alphaEff;
    fvScalarMatrix TEqn
    (
        fvm::ddt(heatCapacityRatio, T)
      + fvm::div(phi, T)
      - fvm::laplacian(alphaEff, T)
    );
    TEqn.solve();
    rhok = 1.0 - beta*(T - TRef);
    // Use the very same discretized boundary flux as the energy equation.
    // Only final PIMPLE iteration advances the integral for this time step.
    if (pimple.finalIter())
    {
        tmp<surfaceScalarField> equationFlux = TEqn.flux();
        scalar outward = 0;
        forAll(mesh.boundary(), patchi)
        {
            if (!mesh.boundary()[patchi].coupled())
                outward += gSum(equationFlux().boundaryField()[patchi]);
        }
        cumulativeHeat -= runTime.deltaTValue()*outward;
    }
}
