// SPDX-License-Identifier: GPL-3.0-or-later
// OpenFOAM 유한체적 연산자를 사용한다. C는 정규화된 공극 내 농도이다.
#include "fvCFD.H"
#include <chrono>

int main(int argc, char *argv[])
{
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createMesh.H"
    volScalarField C(IOobject("C", runTime.timeName(), mesh, IOobject::MUST_READ, IOobject::AUTO_WRITE), mesh);
    // 재개 시에도 공간 계수는 보존된 초기 디렉터리에서 읽는다.
    volScalarField eps(IOobject("eps", "0", mesh, IOobject::MUST_READ, IOobject::NO_WRITE), mesh);
    volScalarField K(IOobject("K", "0", mesh, IOobject::MUST_READ, IOobject::NO_WRITE), mesh);
    volVectorField U(IOobject("U", "0", mesh, IOobject::MUST_READ, IOobject::NO_WRITE), mesh);
    volScalarField Q(IOobject("Q", runTime.timeName(), mesh, IOobject::MUST_READ, IOobject::AUTO_WRITE), mesh);
    volScalarField kAds(IOobject("kAds", "0", mesh, IOobject::MUST_READ, IOobject::NO_WRITE), mesh);
    volScalarField kDes(IOobject("kDes", "0", mesh, IOobject::MUST_READ, IOobject::NO_WRITE), mesh);
    // 공급원이 없던 기존 검증 케이스를 수정하지 않고 재사용할 수 있게 한다.
    volScalarField sourceRate(IOobject("sourceRate", "0", mesh, IOobject::READ_IF_PRESENT, IOobject::NO_WRITE), mesh,
        dimensionedScalar("zero", dimless/dimTime, 0));
    IOdictionary controls(IOobject("transportControl", "constant", mesh, IOobject::READ_IF_PRESENT, IOobject::NO_WRITE));
    const scalar sourceEnd = controls.lookupOrDefault<scalar>("sourceEnd", 0);
    const bool steadyEnabled = controls.lookupOrDefault<bool>("steadyEnabled", false);
    const scalar relRate = controls.lookupOrDefault<scalar>("relativeRate", 1e-4);
    const scalar absRate = controls.lookupOrDefault<scalar>("absoluteRate", 1e-8);
    const scalar holdTime = controls.lookupOrDefault<scalar>("holdTime", 1);
    const scalar minimumTime = controls.lookupOrDefault<scalar>("minimumTime", 1);
    const scalar supplyPerSecond = fvc::domainIntegrate(sourceRate).value();
    scalar supplied = 0, qualified = 0;
    bool steadyReached = false;
    const auto wallStart = std::chrono::steady_clock::now();
    // U는 공극 속도가 아닌 겉보기 속도이다. phi에 공극률을 중복 곱하지 않는다.
    surfaceScalarField phi("phi", fvc::flux(U));
    // 등간격 직교 격자에서 조화 평균 전도도로 경계면 확산 유속을 보존한다.
    surfaceScalarField Kf("Kf", scalar(1)/fvc::interpolate(scalar(1)/K));
    const scalar initial = fvc::domainIntegrate(eps*C + Q).value();
    Info().precision(16);
    Info<< "MASS " << runTime.value() << " " << fvc::domainIntegrate(eps*C).value() << " " << gMin(C) << " " << gMax(C) << endl;
    Info<< "SORBED " << runTime.value() << " " << fvc::domainIntegrate(Q).value() << " " << gMin(Q) << " " << gMax(Q) << endl;
    while (runTime.loop())
    {
        volScalarField previousC("previousC", C);
        const scalar dt = runTime.deltaTValue();
        // 공급 종료가 시간 격자와 어긋나도 실제 공급 구간의 겹침 길이로 적분한다.
        const scalar activeDt = max(scalar(0), min(runTime.value(), sourceEnd)
            - max(scalar(0), runTime.value()-dt));
        supplied += activeDt*supplyPerSecond;
        // 후진 Euler 연립식에서 Q를 소거한다. 양쪽에 같은 교환항을 적용하여
        // 농도를 잘라내지 않고도 기상+흡착상 총량을 보존한다.
        volScalarField previousQ("previousQ", Q);
        volScalarField denominator("denominator", scalar(1) + runTime.deltaT()*kDes);
        fvScalarMatrix equation(fvm::ddt(eps,C) + fvm::div(phi,C) - fvm::laplacian(Kf,C)
            + fvm::Sp(kAds/denominator,C) == (kDes/denominator)*previousQ + (activeDt/dt)*sourceRate);
        equation.solve();
        Q=(previousQ + runTime.deltaT()*kAds*C)/denominator;
        const scalar gasMass = fvc::domainIntegrate(eps*C).value();
        const scalar sorbedMass = fvc::domainIntegrate(Q).value();
        const scalar mass = gasMass+sorbedMass;
        Info<< "MASS " << runTime.value() << " " << gasMass << " " << gMin(C) << " " << gMax(C) << endl;
        Info<< "SORBED " << runTime.value() << " " << sorbedMass << " " << gMin(Q) << " " << gMax(Q) << endl;
        const scalar budgetError = mag(mass-initial-supplied)/max(mag(initial)+supplied, scalar(1e-15));
        if (gMin(C) < -1e-10 || gMin(Q) < -1e-10 || budgetError > 1e-7)
        {
            FatalErrorInFunction << "Positivity or source-adjusted mass balance failed" << exit(FatalError);
        }
        const scalar cRate = gMax(mag(C.primitiveField()-previousC.primitiveField()))/dt;
        const scalar qRate = gMax(mag(Q.primitiveField()-previousQ.primitiveField()))/dt;
        const bool eligible = runTime.value()-dt >= max(sourceEnd, minimumTime);
        const bool stable = cRate <= absRate + relRate*gMax(mag(C.primitiveField()))
            && qRate <= absRate + relRate*gMax(mag(Q.primitiveField())) && budgetError <= 1e-8;
        qualified = (eligible && stable) ? qualified+dt : 0;
        Info<< "PROGRESS " << runTime.value() << " "
            << std::chrono::duration<double>(std::chrono::steady_clock::now()-wallStart).count()
            << " " << cRate << " " << qRate << " " << budgetError << " " << qualified << endl;
        runTime.write();
        if (steadyEnabled && qualified+SMALL >= holdTime)
        {
            runTime.writeNow();
            steadyReached = true;
            Info<< "STOP_REASON steady " << runTime.value() << endl;
            break;
        }
    }
    if (!steadyReached) Info<< "STOP_REASON time_limit " << runTime.value() << endl;
    Info<< "End" << endl;
    return 0;
}
