{
    const scalar mass = fvc::domainIntegrate(eps*C).value();
    const scalar heatChange = fvc::domainIntegrate(heatCapacityRatio*T).value() - initialHeat;
    Info<< "COUPLED " << runTime.value() << ' ' << mass << ' '
        << heatChange << ' ' << cumulativeHeat << ' '
        << gMax(mag(U.primitiveField())) << ' '
        << gMin(T.primitiveField()) << ' ' << gMax(T.primitiveField()) << ' '
        << gMin(C.primitiveField()) << ' ' << gMax(C.primitiveField()) << ' '
        << gMax(mag(fvc::div(phi)().primitiveField())) << endl;
}
