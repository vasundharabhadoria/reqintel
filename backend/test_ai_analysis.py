import asyncio

from services.ai_analysis import AIAnalysisService


async def main():
    service = AIAnalysisService()

    result = await service.analyze_requirement(
        requirement_text="The system shall allow authorized librarians to log in.",
        rule_findings=[
            {
                "rule_name": "Actor Presence",
                "passed": True,
                "severity": "Low",
                "message": "The requirement identifies the actor."
            },
            {
                "rule_name": "Action Presence",
                "passed": True,
                "severity": "Low",
                "message": "The requirement contains a clear action."
            }
        ],
        master_rules=[]
    )

    print("\n===== AI ANALYSIS RESULT =====")
    print("Summary:")
    print(result.analysis_summary)

    print("\nAmbiguity:")
    print(result.ambiguity_detected)

    print("\nIssues:")
    for issue in result.issues:
        print("-", issue)

    print("\nSuggestions:")
    for suggestion in result.suggestions:
        print("-", suggestion.suggestion_text)
        print("  Type:", suggestion.suggestion_type)

    print("\nQuality Assessment:")
    print(result.quality_assessment)


if __name__ == "__main__":
    asyncio.run(main())