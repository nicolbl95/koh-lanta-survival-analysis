from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path.cwd()

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "survival_analysis_final"
    / "manual_physical_v2"
    / "koh_lanta_analysis_ready_manual_physical_v4_blocks5.csv"
)

SOURCE_REPORT = (
    PROJECT_ROOT
    / "report"
    / "koh_lanta_rapport_final_v16.html"
)

OUTPUT_REPORT = (
    PROJECT_ROOT
    / "report"
    / "koh_lanta_rapport_final_v17.html"
)

RESULTS_CSV = (
    PROJECT_ROOT
    / "report"
    / "journey_conditional_adjusted_v17.csv"
)

EXIT_IMAGES_DIR = (
    PROJECT_ROOT
    / "report"
    / "assets"
    / "types_sortie"
)

EXIT_IMAGE_FILES = {
    "Conseil": "conseil.jpg",
    "Blessure / médical": "medical.jpg",
    "Épreuve éliminatoire": "epreuve_eliminatoire.jpg",
    "Abandon volontaire": "abandon.jpg",
    "Ambassadeurs": "ambassadeurs.jpg",
    "Orientation": "orientation.jpg",
    "Poteaux": "poteaux.jpg",
    "Défaite au jury final": "jury_final.jpg",
    "Vainqueur / co-vainqueur": "vainqueur.jpg",
}


# ============================================================
# OUTILS
# ============================================================

def check_files() -> None:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            "\nDataset introuvable :\n"
            f"{DATA_PATH}\n\n"
            "Vérifie le chemin DATA_PATH au début du script."
        )

    if not SOURCE_REPORT.exists():
        raise FileNotFoundError(
            "\nRapport v16 introuvable :\n"
            f"{SOURCE_REPORT}\n\n"
            "Place le rapport v16 dans le dossier report/."
        )


def image_to_data_uri(path: Path) -> str | None:
    if not path.exists():
        return None

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }

    mime = mime_types.get(path.suffix.lower())

    if mime is None:
        return None

    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def figure_to_data_uri(fig: plt.Figure) -> str:
    buffer = io.BytesIO()

    fig.savefig(
        buffer,
        format="png",
        dpi=190,
        bbox_inches="tight",
    )

    plt.close(fig)

    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def format_percentage(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"

    return f"{100 * float(value):.1f} %".replace(".", ",")


def format_pvalue(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "—"

    value = float(value)

    if value < 0.001:
        return "&lt; 0,001"

    return f"{value:.3f}".replace(".", ",")


def dataframe_to_html(
    dataframe: pd.DataFrame,
    escape: bool = False,
) -> str:
    return (
        '<div class="table-wrap">'
        + dataframe.to_html(
            index=False,
            border=0,
            escape=escape,
            classes="report-table",
        )
        + "</div>"
    )


def normalize_block(value: object) -> str:
    text = str(value).strip().lower()

    if text in {"1–5", "1-5"}:
        return "1–5"

    if text in {"6–10", "6-10"}:
        return "6–10"

    if text in {"11–15", "11-15"}:
        return "11–15"

    if "final" in text or "orientation" in text:
        return "Phase finale"

    return str(value)


# ============================================================
# PRÉPARATION DES DONNÉES
# ============================================================

def prepare_dataset() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)

    required_columns = {
        "season_id",
        "season_name",
        "gender",
        "age_band",
        "physical_score",
        "prefinal_block_5",
        "final_departure_cause",
    }

    missing = required_columns.difference(df.columns)

    if missing:
        raise ValueError(
            "Colonnes manquantes dans le dataset : "
            + ", ".join(sorted(missing))
        )

    df = df.copy()

    df["sex_group"] = df["gender"].map(
        {
            "FEMALE": "Femme",
            "MALE": "Homme",
            "Femme": "Femme",
            "Homme": "Homme",
        }
    )

    df["age_group"] = df["age_band"].map(
        {
            "18-25": "18–25 ans",
            "26-33": "26–33 ans",
            "34-41": "34–41 ans",
            "42+": "42 ans et plus",
            "18–25 ans": "18–25 ans",
            "26–33 ans": "26–33 ans",
            "34–41 ans": "34–41 ans",
            "42 ans et plus": "42 ans et plus",
        }
    )

    df["physical_profile"] = df["physical_score"].map(
        {
            0: "Profil non physique",
            1: "Profil physique",
        }
    )

    df["journey_block"] = df["prefinal_block_5"].map(
        normalize_block
    )

    df["winner"] = (
        df["final_departure_cause"]
        .eq("CENSORED_WINNER")
        .astype(int)
    )

    return df


# ============================================================
# PHASES CONDITIONNELLES
# ============================================================

PHASES = [
    {
        "name": "1–5",
        "label": "1–5\nPremiers éliminés",
        "eligible_blocks": {
            "1–5",
            "6–10",
            "11–15",
            "Phase finale",
        },
        "event_block": "1–5",
        "final_phase": False,
    },
    {
        "name": "6–10",
        "label": "6–10\nDeuxième phase",
        "eligible_blocks": {
            "6–10",
            "11–15",
            "Phase finale",
        },
        "event_block": "6–10",
        "final_phase": False,
    },
    {
        "name": "11–15",
        "label": "11–15\nTroisième phase",
        "eligible_blocks": {
            "11–15",
            "Phase finale",
        },
        "event_block": "11–15",
        "final_phase": False,
    },
    {
        "name": "Phase finale",
        "label": "Phase finale",
        "eligible_blocks": {
            "Phase finale",
        },
        "event_block": None,
        "final_phase": True,
    },
]


VARIABLES = {
    "Sexe": {
        "column": "sex_group",
        "modalities": ["Homme", "Femme"],
        "reference": "Femme",
    },
    "Profil physique": {
        "column": "physical_profile",
        "modalities": [
            "Profil physique",
            "Profil non physique",
        ],
        "reference": "Profil non physique",
    },
    "Âge": {
        "column": "age_group",
        "modalities": [
            "18–25 ans",
            "26–33 ans",
            "34–41 ans",
            "42 ans et plus",
        ],
        "reference": "26–33 ans",
    },
}


def create_phase_dataset(
    df: pd.DataFrame,
    phase: dict,
) -> pd.DataFrame:
    phase_df = df[
        df["journey_block"].isin(phase["eligible_blocks"])
    ].copy()

    if phase["final_phase"]:
        phase_df["phase_eliminated"] = 1 - phase_df["winner"]
    else:
        phase_df["phase_eliminated"] = (
            phase_df["journey_block"]
            .eq(phase["event_block"])
            .astype(int)
        )

    return phase_df


def fit_phase_model(
    phase_df: pd.DataFrame,
):
    formula = (
        "phase_eliminated ~ "
        "C(sex_group, Treatment(reference='Femme')) + "
        "C(age_group, Treatment(reference='26–33 ans')) + "
        "physical_score + "
        "C(season_id)"
    )

    try:
        model = smf.glm(
            formula=formula,
            data=phase_df,
            family=sm.families.Binomial(),
        ).fit()

        return model

    except Exception as error:
        print(
            "\nImpossible d’ajuster un modèle :",
            error,
        )

        return None


def get_coefficient_pvalue(
    model,
    variable_name: str,
    modality: str,
) -> float | None:
    if model is None:
        return None

    if variable_name == "Sexe":
        if modality == "Femme":
            return None

        coefficient = (
            "C(sex_group, Treatment(reference='Femme'))"
            "[T.Homme]"
        )

    elif variable_name == "Profil physique":
        if modality == "Profil non physique":
            return None

        coefficient = "physical_score"

    elif variable_name == "Âge":
        if modality == "26–33 ans":
            return None

        coefficient = (
            "C(age_group, Treatment(reference='26–33 ans'))"
            f"[T.{modality}]"
        )

    else:
        return None

    if coefficient in model.pvalues.index:
        return float(model.pvalues[coefficient])

    return None


def adjusted_probability(
    model,
    phase_df: pd.DataFrame,
    variable_name: str,
    modality: str,
) -> float | None:
    if model is None:
        return None

    prediction_df = phase_df.copy()

    if variable_name == "Sexe":
        prediction_df["sex_group"] = modality

    elif variable_name == "Profil physique":
        prediction_df["physical_profile"] = modality
        prediction_df["physical_score"] = (
            1 if modality == "Profil physique" else 0
        )

    elif variable_name == "Âge":
        prediction_df["age_group"] = modality

    predictions = model.predict(prediction_df)

    return float(np.mean(predictions))


def build_conditional_journey_results(
    df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for phase in PHASES:
        phase_df = create_phase_dataset(df, phase)
        model = fit_phase_model(phase_df)

        for variable_name, config in VARIABLES.items():
            column = config["column"]

            for modality in config["modalities"]:
                modality_df = phase_df[
                    phase_df[column].eq(modality)
                ]

                n_at_start = len(modality_df)

                n_eliminated = int(
                    modality_df["phase_eliminated"].sum()
                )

                raw_probability = (
                    n_eliminated / n_at_start
                    if n_at_start > 0
                    else np.nan
                )

                adjusted = adjusted_probability(
                    model=model,
                    phase_df=phase_df,
                    variable_name=variable_name,
                    modality=modality,
                )

                pvalue = get_coefficient_pvalue(
                    model=model,
                    variable_name=variable_name,
                    modality=modality,
                )

                rows.append(
                    {
                        "Phase": phase["name"],
                        "Libellé": phase["label"],
                        "Variable": variable_name,
                        "Modalité": modality,
                        "N au début de la phase": n_at_start,
                        "Éliminés durant la phase": n_eliminated,
                        "Probabilité brute conditionnelle": raw_probability,
                        "Probabilité ajustée conditionnelle": adjusted,
                        "p-value": pvalue,
                    }
                )

    return pd.DataFrame(rows)


# ============================================================
# GRAPHIQUES DU PARCOURS
# ============================================================

def build_journey_plot(
    results: pd.DataFrame,
    variable_name: str,
    title: str,
) -> str:
    config = VARIABLES[variable_name]

    fig, ax = plt.subplots(
        figsize=(11.5, 6.4)
    )

    for modality in config["modalities"]:
        subset = results[
            results["Variable"].eq(variable_name)
            & results["Modalité"].eq(modality)
        ].copy()

        subset["Phase"] = pd.Categorical(
            subset["Phase"],
            categories=[
                phase["name"]
                for phase in PHASES
            ],
            ordered=True,
        )

        subset = subset.sort_values("Phase")

        x_labels = subset["Libellé"].tolist()

        y_values = (
            subset["Probabilité ajustée conditionnelle"]
            .astype(float)
            .mul(100)
            .tolist()
        )

        ax.plot(
            x_labels,
            y_values,
            marker="o",
            linewidth=2.2,
            markersize=7,
            label=modality,
        )

        for x_value, y_value in zip(
            x_labels,
            y_values,
        ):
            ax.text(
                x_value,
                y_value + 1,
                f"{y_value:.1f} %".replace(".", ","),
                ha="center",
                fontsize=8,
            )

    ax.set_title(title)
    ax.set_xlabel("Phase du parcours")

    ax.set_ylabel(
        "Probabilité ajustée d’être éliminé "
        "durant la phase (%)"
    )

    ax.grid(alpha=0.22)

    ax.legend(
        title=variable_name,
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
    )

    fig.tight_layout()

    return figure_to_data_uri(fig)


def build_journey_table(
    results: pd.DataFrame,
    variable_name: str,
) -> pd.DataFrame:
    table = results[
        results["Variable"].eq(variable_name)
    ].copy()

    phase_labels = {
        "1–5": "1–5 — Premiers éliminés",
        "6–10": "6–10 — Deuxième phase",
        "11–15": "11–15 — Troisième phase",
        "Phase finale": "Phase finale",
    }

    table["Phase"] = table["Phase"].map(
        phase_labels
    )

    table[
        "Probabilité brute conditionnelle"
    ] = table[
        "Probabilité brute conditionnelle"
    ].map(format_percentage)

    table[
        "Probabilité ajustée conditionnelle"
    ] = table[
        "Probabilité ajustée conditionnelle"
    ].map(format_percentage)

    table["p-value"] = table["p-value"].map(
        format_pvalue
    )

    return table[
        [
            "Phase",
            "Modalité",
            "N au début de la phase",
            "Éliminés durant la phase",
            "Probabilité brute conditionnelle",
            "Probabilité ajustée conditionnelle",
            "p-value",
        ]
    ]


# ============================================================
# CONTEXTE DU PROJET
# ============================================================

def build_seasons_table(
    df: pd.DataFrame,
) -> str:
    seasons = (
        df[
            [
                "season_id",
                "season_name",
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    seasons["season_number"] = (
        seasons["season_id"]
        .astype(str)
        .str.extract(
            r"(\d+)",
            expand=False,
        )
        .astype(float)
    )

    seasons = seasons.sort_values(
        [
            "season_number",
            "season_id",
        ]
    )

    seasons = seasons.rename(
        columns={
            "season_id": "Identifiant du dataset",
            "season_name": "Saison retenue",
        }
    )

    return dataframe_to_html(
        seasons[
            [
                "Identifiant du dataset",
                "Saison retenue",
            ]
        ]
    )


def build_project_context_html(
    df: pd.DataFrame,
) -> str:
    seasons_table = build_seasons_table(df)

    return f"""
<h2>1. Présentation de Koh-Lanta</h2>

<p>
<strong>Koh-Lanta</strong> est une émission française d’aventure et de
compétition diffusée depuis 2001. Des candidats sont isolés pendant
plusieurs semaines dans un environnement tropical, avec peu de nourriture
et des conditions de vie difficiles. Ils participent à des épreuves,
contribuent à la survie du camp et cherchent à éviter les différents
mécanismes d’élimination. La compétition commence généralement par une
phase en tribus, puis devient individuelle après la réunification.
Les éliminations se poursuivent jusqu’aux épreuves finales et au vote
du jury final. Le programme combine ainsi capacités physiques,
endurance, adaptation, stratégie et relations sociales.
</p>

<h2>2. Pourquoi ce projet ?</h2>

<p>
Koh-Lanta constitue un cas d’étude accessible pour analyser un parcours
compétitif dans lequel plusieurs événements peuvent interrompre la
progression d’un individu : vote, blessure, abandon, défaite lors d’une
épreuve ou élimination pendant la finale. Cette structure ressemble à
des problèmes professionnels de churn client, de parcours salarié,
de risque médical ou de risque de crédit. Le projet transforme ainsi
un sujet populaire en un pipeline complet de collecte, enrichissement,
validation, modélisation et communication de données.
</p>

<h2>3. Historique et périmètre</h2>

<p>
Koh-Lanta a commencé en 2001. L’émission comprend des saisons classiques,
des éditions réunissant d’anciens candidats et plusieurs formats spéciaux.
L’analyse statistique présentée ici ne porte pas sur toutes les éditions.
Elle retient 17 saisons et 340 candidats répondant aux critères de
comparabilité et de qualité des données du projet.
</p>

<h3>Saisons retenues</h3>

{seasons_table}

<p>
Les saisons retenues comportent principalement de nouveaux candidats,
un ordre de sortie exploitable et des mécanismes de départ suffisamment
documentés. Leur format permet également de comparer le parcours des
candidats sans que la compétition soit entièrement structurée dès le
départ par l’une des variables étudiées.
</p>

<h3>Saisons non retenues</h3>

<p>
Les éditions All Stars et les saisons principalement composées d’anciens
candidats ont été exclues. Les participants revenants disposent déjà
d’une expérience du jeu, d’une réputation et parfois de relations
préexistantes. Ils ne sont donc pas directement comparables à de
nouveaux candidats.
</p>

<p>
Les formats hybrides mélangeant anciens et nouveaux candidats ont
également été écartés. L’expérience et la notoriété des revenants
peuvent influencer les alliances, les votes et la perception des menaces.
</p>

<p>
Certaines saisons structurées dès le départ selon une caractéristique
directement étudiée, comme l’âge ou le sexe, n’ont pas été retenues.
Dans ces formats, il devient difficile de distinguer l’effet individuel
de la variable de l’effet produit par la composition imposée des tribus.
</p>

<p>
Enfin, certaines saisons ont été exclues lorsque les données disponibles
ne permettaient pas de reconstruire avec suffisamment de fiabilité
l’ordre définitif des départs, les retours dans le jeu ou le mécanisme
exact de sortie.
</p>

<h2>4. Question de recherche</h2>

<p>
La question principale du projet est la suivante :
<strong>dans quelle mesure l’âge, le sexe et le profil physique sont-ils
associés au parcours d’un candidat dans Koh-Lanta, depuis les premières
éliminations jusqu’aux étapes finales et à la victoire ?</strong>
</p>

<p>
L’analyse cherche à mesurer des associations et non à démontrer des
relations causales. Elle compare les résultats directement observés,
puis utilise des modèles ajustés afin de contrôler simultanément les
autres variables et les différences entre saisons.
</p>

<h2>5. Variables retenues</h2>

<h3>Âge</h3>

<p>
L’âge peut potentiellement influencer la récupération, l’endurance,
la résistance aux privations et le risque de blessure. Les candidats
les plus jeunes peuvent disposer d’avantages physiques, mais aussi de
moins d’expérience sociale ou stratégique. Les candidats plus âgés
peuvent être davantage exposés à la fatigue, tout en bénéficiant d’une
meilleure stabilité émotionnelle et d’une meilleure lecture des
relations. L’intuition initiale était donc que l’effet de l’âge pouvait
varier selon la phase de l’émission.
</p>

<h3>Sexe</h3>

<p>
Le sexe peut être associé aux performances dans certaines épreuves,
mais aussi à la manière dont l’utilité physique, le rôle dans la tribu
ou la menace stratégique sont perçus. Certaines épreuves favorisent
la puissance ou la vitesse, tandis que d’autres reposent davantage
sur l’équilibre, la précision, l’endurance ou la concentration.
L’hypothèse de départ n’était donc pas qu’un sexe serait toujours
avantagé, mais que les différences pourraient évoluer selon les phases.
</p>

<h3>Profil physique</h3>

<p>
Le profil physique a été retenu parce que les capacités corporelles
occupent une place importante dans Koh-Lanta. Un candidat sportif peut
être utile à sa tribu et mieux protégé lors des premières éliminations.
Après la réunification, ce même candidat peut toutefois être considéré
comme une menace. L’hypothèse initiale était donc qu’un profil physique
pouvait représenter un avantage au début de l’aventure, puis perdre
de son importance ou devenir un risque stratégique plus tard.
</p>

<h3>Une variable moins standardisée</h3>

<p>
La variable physique est plus difficile à mesurer que l’âge ou le sexe.
Une première tentative d’automatisation a utilisé les professions,
les biographies et les mentions de pratiques sportives disponibles.
Les résultats ne correspondaient cependant pas toujours à la réalité
observable.
</p>

<p>
La classification a donc été réalisée manuellement, candidat par
candidat, à partir de plusieurs indices : parcours sportif, profession,
gabarit apparent, musculature et informations biographiques.
Cette approche human-in-the-loop a permis de corriger les erreurs
d’une classification purement automatisée, mais la variable reste
<strong>moins standardisée et partiellement subjective</strong>.
Les résultats liés au profil physique doivent donc être interprétés
avec davantage de prudence.
</p>

<h3>Variables qui auraient également pu être étudiées</h3>

<p>
D’autres facteurs pourraient jouer un rôle important : profession,
taille, poids, morphologie, niveau sportif détaillé, composition de la
tribu, performances aux épreuves, avantages, immunités, alliances et
position sociale. Ils n’ont pas été inclus dans cette version parce
qu’ils n’étaient pas disponibles de manière homogène et fiable pour
l’ensemble des candidats.
</p>

<p>
Les alliances seraient particulièrement intéressantes, mais leur
reconstruction demanderait une analyse épisode par épisode,
l’extraction des votes et la création d’un graphe social dynamique.
Cela pourrait constituer une extension future fondée sur l’extraction
d’informations par LLM.
</p>

<h2>6. Méthodologie résumée</h2>

<p>
Le projet repose sur un pipeline combinant scraping de sources
encyclopédiques, normalisation des candidats et des saisons,
classification des mécanismes de sortie, enrichissement assisté par LLM,
validation humaine, contrôles automatisés et modélisation statistique.
Les détails techniques et les instructions de reproduction seront
documentés dans le dépôt GitHub.
</p>
"""


# ============================================================
# TYPES DE SORTIE
# ============================================================

EXIT_DESCRIPTIONS = {
    "Conseil": (
        "Le Conseil est le principal mécanisme d’élimination. "
        "Les candidats votent pour désigner l’aventurier qui doit "
        "quitter le jeu. Les sorties liées aux destins liés sont "
        "intégrées à cette catégorie lorsque le vote contre un membre "
        "provoque aussi la sortie de son partenaire."
    ),
    "Blessure / médical": (
        "Un candidat peut être contraint de quitter l’aventure lorsque "
        "le médecin estime que son état de santé ne lui permet plus de "
        "continuer sans danger. Cette catégorie inclut les blessures, "
        "malaises et autres décisions médicales définitives."
    ),
    "Épreuve éliminatoire": (
        "Certaines épreuves entraînent directement l’élimination du "
        "candidat qui termine dernier ou échoue à atteindre l’objectif. "
        "La sortie dépend du résultat de l’épreuve et non d’un vote."
    ),
    "Abandon volontaire": (
        "Un candidat peut décider de quitter volontairement l’émission "
        "pour une raison personnelle, psychologique, familiale ou "
        "physique. Cette catégorie est distincte d’une sortie imposée "
        "par le médecin."
    ),
    "Ambassadeurs": (
        "Lors de la réunification, des représentants des anciennes "
        "tribus doivent parfois désigner un candidat à éliminer. "
        "En cas de désaccord, certaines saisons prévoient un tirage "
        "au sort ou une autre procédure."
    ),
    "Orientation": (
        "L’orientation est une épreuve finale de recherche. "
        "Les candidats doivent trouver un repère puis localiser un "
        "poignard. Le dernier candidat qui ne trouve pas de poignard "
        "est éliminé."
    ),
    "Poteaux": (
        "Les candidats doivent rester en équilibre le plus longtemps "
        "possible sur des plateformes qui deviennent progressivement "
        "plus étroites. Le vainqueur choisit généralement la personne "
        "qui l’accompagnera devant le jury final."
    ),
    "Défaite au jury final": (
        "Les finalistes présentent leur parcours devant un jury composé "
        "d’anciens candidats éliminés. Le jury vote pour désigner le "
        "vainqueur ; les autres finalistes sont classés dans cette "
        "catégorie."
    ),
    "Vainqueur / co-vainqueur": (
        "Le candidat recevant le plus de votes du jury est considéré "
        "comme vainqueur. Certaines éditions ont produit des "
        "co-vainqueurs ; tous sont traités comme gagnants dans le dataset."
    ),
}


def build_exit_types_html() -> str:
    cards = []

    for title, description in EXIT_DESCRIPTIONS.items():
        image_filename = EXIT_IMAGE_FILES.get(title)
        image_uri = None

        if image_filename:
            image_uri = image_to_data_uri(
                EXIT_IMAGES_DIR / image_filename
            )

        image_html = ""

        if image_uri:
            image_html = (
                f'<img class="exit-card-image" '
                f'src="{image_uri}" '
                f'alt="{title}">'
            )

        cards.append(
            f"""
<div class="exit-card">
    {image_html}
    <div class="exit-card-content">
        <h3>{title}</h3>
        <p>{description}</p>
    </div>
</div>
"""
        )

    return f"""
<h2>7. Comprendre les types de sortie</h2>

<p>
Les mécanismes suivants correspondent aux causes finales utilisées dans
le dataset. Ils permettent de distinguer une élimination stratégique,
une sortie médicale, une défaite lors d’une épreuve et les différentes
étapes de la finale.
</p>

<div class="exit-grid">
    {''.join(cards)}
</div>
"""


# ============================================================
# NOUVELLE SECTION DU PARCOURS
# ============================================================

def build_conditional_journey_html(
    results: pd.DataFrame,
) -> str:
    sex_plot = build_journey_plot(
        results,
        "Sexe",
        "Probabilité conditionnelle d’élimination selon le sexe",
    )

    physical_plot = build_journey_plot(
        results,
        "Profil physique",
        "Probabilité conditionnelle d’élimination selon le profil physique",
    )

    age_plot = build_journey_plot(
        results,
        "Âge",
        "Probabilité conditionnelle d’élimination selon l’âge",
    )

    sex_table = dataframe_to_html(
        build_journey_table(
            results,
            "Sexe",
        ),
        escape=False,
    )

    physical_table = dataframe_to_html(
        build_journey_table(
            results,
            "Profil physique",
        ),
        escape=False,
    )

    age_table = dataframe_to_html(
        build_journey_table(
            results,
            "Âge",
        ),
        escape=False,
    )

    return f"""
<h2>9. Probabilité conditionnelle d’élimination par phase</h2>

<p>
Pour chaque phase, le calcul inclut uniquement les candidats encore
en compétition au début de cette phase. Une personne éliminée pendant
les cinq premières sorties n’est donc plus incluse dans le dénominateur
de la phase suivante.
</p>

<p>
Cette méthode répond à la question :
<strong>parmi les candidats ayant effectivement atteint cette phase,
quelle est la probabilité d’être éliminé pendant celle-ci ?</strong>
</p>

<p class="footnote">
<strong>* Données brutes :</strong> proportions directement observées
parmi les candidats encore présents au début de la phase.
<strong>Données ajustées :</strong> probabilités estimées après contrôle
simultané du sexe, de l’âge, du profil physique et de la saison.
</p>

<h3>Selon le sexe</h3>

<figure>
    <img src="{sex_plot}" alt="Parcours conditionnel selon le sexe">
    <figcaption>
        Données ajustées sur l’âge, le profil physique et la saison.
    </figcaption>
</figure>

{sex_table}

<h3>Selon le profil physique</h3>

<figure>
    <img
        src="{physical_plot}"
        alt="Parcours conditionnel selon le profil physique"
    >
    <figcaption>
        Données ajustées sur le sexe, l’âge et la saison.
    </figcaption>
</figure>

{physical_table}

<h3>Selon l’âge</h3>

<figure>
    <img src="{age_plot}" alt="Parcours conditionnel selon l’âge">
    <figcaption>
        Données ajustées sur le sexe, le profil physique et la saison.
    </figcaption>
</figure>

{age_table}
"""


# ============================================================
# MODIFICATION DU HTML
# ============================================================

def add_css(html_text: str) -> str:
    extra_css = """
<style>
.exit-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px;
    margin: 24px 0 34px;
}

.exit-card {
    border: 1px solid #d1d5db;
    border-radius: 10px;
    overflow: hidden;
    background: #ffffff;
}

.exit-card-image {
    display: block;
    width: 100%;
    height: 210px;
    object-fit: cover;
}

.exit-card-content {
    padding: 16px 18px;
}

.exit-card-content h3 {
    margin-top: 0;
    margin-bottom: 8px;
}

.exit-card-content p {
    margin: 0;
}

.footnote {
    background: #f8fafc;
    border-left: 4px solid #64748b;
    padding: 14px 17px;
    font-size: 0.92rem;
}

@media (max-width: 800px) {
    .exit-grid {
        grid-template-columns: 1fr;
    }
}
</style>
"""

    return html_text.replace(
        "</head>",
        extra_css + "\n</head>",
        1,
    )


def remove_old_intro(
    html_text: str,
) -> str:
    pattern = re.compile(
        r"<h2>1\.\s*Comment lire les résultats</h2>.*?"
        r"(?=<h2>2\.)",
        flags=re.DOTALL,
    )

    return pattern.sub(
        "",
        html_text,
        count=1,
    )


def insert_new_context(
    html_text: str,
    context_html: str,
) -> str:
    match = re.search(
        r"<h2>2\.\s*Types de sortie par saison</h2>",
        html_text,
    )

    if not match:
        raise ValueError(
            "La section Types de sortie par saison "
            "n’a pas été trouvée."
        )

    position = match.start()

    return (
        html_text[:position]
        + context_html
        + "\n"
        + html_text[position:]
    )


def insert_exit_explanations(
    html_text: str,
    exit_html: str,
) -> str:
    old_heading = (
        "<h2>2. Types de sortie par saison</h2>"
    )

    if old_heading not in html_text:
        raise ValueError(
            "Le titre Types de sortie par saison "
            "n’a pas été trouvé."
        )

    replacement = (
        exit_html
        + "\n"
        + "<h2>8. Types de sortie par saison</h2>"
    )

    return html_text.replace(
        old_heading,
        replacement,
        1,
    )


def replace_old_journey_section(
    html_text: str,
    new_journey_html: str,
) -> str:
    pattern = re.compile(
        r"<h2>3\.\s*Parcours ajusté par blocs de cinq éliminations</h2>"
        r".*?"
        r"(?=<h2>4\.\s*Étapes finales</h2>)",
        flags=re.DOTALL,
    )

    if not pattern.search(html_text):
        raise ValueError(
            "L’ancienne section du parcours "
            "n’a pas été trouvée."
        )

    return pattern.sub(
        new_journey_html + "\n",
        html_text,
        count=1,
    )


def remove_global_final_stage_chart(
    html_text: str,
) -> str:
    pattern = re.compile(
        r"<h2>4\.\s*Étapes finales</h2>"
        r".*?"
        r"(?=<h3>Selon le sexe</h3>)",
        flags=re.DOTALL,
    )

    replacement = """
<h2>10. Étapes finales</h2>
"""

    if not pattern.search(html_text):
        raise ValueError(
            "Le début de la section Étapes finales "
            "n’a pas été trouvé."
        )

    return pattern.sub(
        replacement,
        html_text,
        count=1,
    )


def remove_mechanism_sensitivity(
    html_text: str,
) -> str:
    pattern = re.compile(
        r"<h2>6\.\s*Sensibilité aux mécanismes de sortie</h2>"
        r".*?"
        r"(?=<h2>7\.\s*Limites générales</h2>)",
        flags=re.DOTALL,
    )

    return pattern.sub(
        "",
        html_text,
        count=1,
    )


def renumber_remaining_sections(
    html_text: str,
) -> str:
    html_text = html_text.replace(
        "<h2>5. Probabilité de gagner Koh-Lanta</h2>",
        "<h2>11. Probabilité de gagner Koh-Lanta</h2>",
        1,
    )

    html_text = html_text.replace(
        "<h2>7. Limites générales</h2>",
        "<h2>12. Limites générales</h2>",
        1,
    )

    return html_text


def update_footer(
    html_text: str,
) -> str:
    pattern = re.compile(
        r"<footer>.*?</footer>",
        flags=re.DOTALL,
    )

    footer = """
<footer>
Version v17 — ajout du contexte de l’émission, justification des variables,
explication des mécanismes de sortie et remplacement des anciens blocs
par des probabilités conditionnelles calculées uniquement parmi les
candidats encore en compétition.
</footer>
"""

    return pattern.sub(
        footer,
        html_text,
        count=1,
    )


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main() -> None:
    check_files()

    print("Lecture du dataset...")
    df = prepare_dataset()

    print("Calcul des probabilités conditionnelles...")
    journey_results = build_conditional_journey_results(
        df
    )

    RESULTS_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    journey_results.to_csv(
        RESULTS_CSV,
        index=False,
        encoding="utf-8-sig",
    )

    print("Création des nouvelles sections...")
    context_html = build_project_context_html(df)
    exit_types_html = build_exit_types_html()

    journey_html = build_conditional_journey_html(
        journey_results
    )

    print("Lecture du rapport v16...")

    report_html = SOURCE_REPORT.read_text(
        encoding="utf-8"
    )

    report_html = add_css(report_html)

    report_html = remove_old_intro(
        report_html
    )

    report_html = insert_new_context(
        report_html,
        context_html,
    )

    report_html = insert_exit_explanations(
        report_html,
        exit_types_html,
    )

    report_html = replace_old_journey_section(
        report_html,
        journey_html,
    )

    report_html = remove_global_final_stage_chart(
        report_html
    )

    report_html = remove_mechanism_sensitivity(
        report_html
    )

    report_html = renumber_remaining_sections(
        report_html
    )

    report_html = update_footer(
        report_html
    )

    OUTPUT_REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_REPORT.write_text(
        report_html,
        encoding="utf-8",
    )

    print("\nRapport généré avec succès :")
    print(OUTPUT_REPORT)

    print("\nTableau de vérification généré :")
    print(RESULTS_CSV)


if __name__ == "__main__":
    main()
