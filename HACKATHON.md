# Shark HD520 AI Companion — Hackathon Submission Notes

## What this is

A local-first AI companion for the Shark HD520 CNC, built around (never inside)
VCarve Pro 11. The cabinet generator proposes geometry; a deterministic rules
engine, nesting, and preflight decide what may become a file. Nothing exports
on a failed preflight, and nothing in this app can start, jog, home, or
otherwise move the machine.

## Pre-existing vs built during the hackathon

Pre-existing (built before the hackathon, Oct 20-25): spec v1.1, the
cabinet-generator prototype, and the Phase 0 profile/worksheet.

Built during the hackathon: the real local app in this repo (REST + MCP,
parity-tested), Meta-central brief handling, and the 34-inch base cut package
(DXF + preflight report). The physical proof cut on the Shark HD520 is still
to come; nothing in this repo has cut anything yet.

## Use of Meta products

Muse Spark (Meta Model API, Standard tier) is the primary input path for
brief-to-parameters: it turns a plain-English brief into generator parameters.
Photo segmentation (SAM 3.1) and relief prep (Muse Image) are planned for later
phases, not in this repo yet. Nesting, tiling, direct toolpath output, and all
preflight gates are deterministic and model-free. Remove Meta and the engine
still cuts safely from manual parameters, but it stops being an AI companion:
no brief understanding, no photo understanding, no plain-English explanations.

## Status

Phase 1 complete: generator engine, REST + MCP with UI/MCP parity (34-inch
base: 16 parts, 10 nesting sheets, identical on both paths), preflight gates,
and a cut-ready DXF for VCarve import. Direct .tap output, photo trace, and
relief are later phases. See outputs/gaps.md for provisional values and open
decisions.
