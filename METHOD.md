# Class-Only Race Analyser — Method v3

## Core principle

The score is intended to answer one question only: **how favourable is today's race class for this horse, based on the class strength it has previously demonstrated?**

Odds, speed, distance suitability, going, jockey, trainer, draw, fitness and weight are not scoring inputs.

## Effective race strength

An R&S `CL1/CL2/CL3/CL4/CL5`, Listed or Group label remains the strongest class signal. The model then refines that nominal level using **race prize money (`$R.PM`)** and **race type**.

This solves the major failure exposed by unlabelled French races. A race shown only as `HCP HDLE EUR €26k` or `CLM EUR €18.2k` is no longer treated as unknown. Instead it receives an internal effective-strength benchmark based on discipline, type and purse. This benchmark is an analytical proxy; it is not presented as an official France Galop class.

## Prize money as a proxy

Prize money is used in two ways:

1. **Within an explicit class**, a higher-purse CL3 is treated as modestly stronger than a lower-purse CL3.
2. **When class is absent**, purse + race type provide the primary class-strength estimate.

Claiming, handicap, conditions and maiden races are not considered equivalent solely because their prize money is similar.

## Performance proof

Simply entering a strong race does not establish class. The model measures how competitive the horse was, using finishing position, field size and margin. Higher-class evidence receives substantial credit only when the run was meaningfully competitive.

Recent evidence receives greater weight than old evidence.

## Class movement

The app evaluates both:

- the **latest same-discipline class movement**, and
- the horse's **best competitively proven class ceiling**.

This allows descriptions such as `Up from latest; below proven ceiling` rather than forcing every horse into a simplistic latest-start comparison.

## Progressing runners

The Deauville result review showed that an improving runner can successfully rise in class after a recent top-three finish at the immediately lower level. The v3 model therefore gives additional progression credit to this pattern without treating it as equivalent to already being proven at today's grade.

## Discipline

For hurdles, hurdle evidence has full weight; steeple form is secondary and Flat form is minor supporting evidence. The corresponding principle applies to steeplechases. Flat races largely ignore jumps evidence.

## Actual-result feedback

The supplied Deauville R1-R8 results from 11 Aug 2026 were used to tune only general class-derived relationships. No horse name or odds feature is part of the result-feedback model. The adjustment is deliberately bounded because actual finishing positions reflect many factors outside class.

## Worked-example anchors

The previously established manual scores are preserved exactly for the four audit examples included in `sample_data`.
